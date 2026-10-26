# Verification — 测试政策、合同守卫与当前验收

> Status: 当前规范（2026-10-26）。本文是测试运行纪律、合同↔守卫映射与跨模块验收的唯一母文档；排期仍归 PROGRESS。测试/文档退役不是产品验收通过，绿色历史标记不等于当前 HEAD 或真实旅程已通过。
>
> 新视频只按 VIDEO_PROJECT 与 video-project-implementation 施工。旧 Film 固定骨架、pending 信封、legacy 指纹和旧 schema 的专属测试不再作为新链兼容目标；共享权限、授权、计费、执行身份、Clip 和消息回放守卫继续有效。新 Composition/时间/spec/旅程覆盖按 A/B 出口补齐，未建覆盖明确记缺口，不用删测试制造“生产已就绪”。

## 1. 测试运行政策

### 1.1 当前资产边界

只保留两类测试资产：

1. **用户主流程旅程矩阵**：各种用户经 chat 完成各类创作流程的全旅程；以 `apps/api/scripts/chat_scenarios.py` 当前 `SCENARIOS` 注册表为准，不在文档复制固定数量。
2. **承重架构防漂移守卫**：唯一写口、依赖方向、registry↔prompt 一致性、执行身份、授权与数据完整性等全站铁律。

事故回归锁、批次产物和镜像实现形态的锁不单独保留。新覆盖必须能指出所属旅程与步骤，或所守的承重合同；重构使测试失去合同依据时逐案删除，不留注释尸体。

### 1.2 当前验证层

- 部署前依次运行纯 pytest、check_gates、prompt 面变化时的 prompt_gate、当前注册旅程矩阵；web 按改动面运行纯 node 测试与类型检查。
- 剧本只锁服务端真值与形态，不锁 LLM 文案；打字机、remount、布局形态等客户端法律归 web 纯测试与 live 走查。
- 仪表脚本用于诊断，不阻塞部署；读数不能替代门禁，也不能为放行调整阈值。
- 测试迁移必须先裁决现行合同；“base 也失败”既不自动证明测试该删，也不证明应保留失败。

### 1.3 Fixture 与 flake 处置

- 剧本素材先复制到 `scenario/` 前缀；项目删除会 unlink 外部共享 key，禁止直接引用营销或用户资产。
- fixture 必须显式建立被测状态；常驻 worker 的时序不得定义剧本语义。手工 run 前后清理数据，修改 pipeline 后重启 worker。
- 断言只锁形态；红先归因机制。可用 pre-批面复跑、固定输入重复采样和失败签名频率区分回归、既有弱点与发射方差，禁止调断言放行。
- 连续出现同类方差时登记 PROGRESS，保留原始输出、工具调用和应用处理证据，不静默重试到绿。

#### 已知方差与覆盖边界

- S1 / S6f / S10 的 baseline LLM 方差是开放观察项，不自动放大为新的 release regression；每次仍需在当前 HEAD 归因。
- prompt_gate I 需以新目标的实际读数完成校准；校准与回归放行是两件事。
- 以下风险目前没有完整活旅程自动化看护：计费失败、孤儿 hold 回收、run 执行权仲裁、turn durability、SSE 断流复连、repair 静默/泄漏。相关纯函数覆盖不能冒充全链覆盖；是否补入矩阵须按用户旅程归属评估。
- 保留历史消息的环境，migrate_activity_log_rows.py 退役前仍须迁移与回放证明；本轮已授权 reset 的无用户环境可重建空数据，不承担旧行兼容回填。reset 未执行不等于旧行已清零。
- trigger `/event/sync` 无 Activity 行是 parity 观察，不自动等同于缺陷或新需求。

### 1.4 Harness 纪律

- **进程卫生**：`uv run` 包装器被 kill 可能留下孤儿 worker；手工 harness 使用 `start_new_session` + `killpg`，结束时核对实际进程。
- **配额**：全量剧本/gate 可能产生显著模型费用；合并改动后一次跑，所有真实模型 HTTP 计入预算，warmup 默认关闭。付费运行需明确授权。
- **探针采样**：需要比较 provider/prompt 时采用 round-robin，避免顺序批把 provider 漂移误判为改动效果；保留原始读数。
- **升编**：scratch 工具一旦被现行文档或部署仪式引用，就应迁入受维护的 harness/scripts 位置；不要长期让关键验收依赖一次性目录。
- **文档**：当前注册表、命令和已知限制就地更新；不保存历史测试输出、调用量日志或旧矩阵副本。
### 1.5 合同迁移原则

1. **Tests protect contracts, not historical implementations.** 测试锁的是
   合同，不是某个历史实现形态；实现替换时测试按合同重审，不按代码怀旧。
2. **Contract migration requires intentional product/architecture change.**
   测试迁移的唯一合法理由是合同被有意变更（有 ADR / 用户拍板）；**永不**
   为了让当前实现变绿而削弱断言。「base 同样失败」不自动等于「测试该留
   失败」，也不自动等于「测试该删」——先裁决合同，再动测试。
3. **Scenario fixtures must explicitly establish the state under test.**
   剧本前置条件由 fixture 显式声明，background worker 的 timing / race
   永不定义剧本语义（fixture 纪律见 `docs/VERIFICATION.md`
   §1.3/§1.4 与 `chat_scenarios.py` 头部）。

## 2. 合同 ↔ 承重守卫映射

剧本座列以 `apps/api/scripts/chat_scenarios.py` 当前 `SCENARIOS` 注册表为准（ADR-114），不在这里固定矩阵数量；「harness 公共断言」= 每本自动携带的 SSE 线格式 / Activity 帧形态 / dock 形态 / 估价三断言。

| Contract | Owner | Canonical source | Pure tests | Scenario / script 座 | Static guards | Status / Known limitations |
|:---|:---|:---|:---|:---|:---|:---|
| Lifecycle 谓词（五态 + 四合取 + blocker 谓词序） | `app/pipeline/lifecycle.py` | ADR-087 §2 + NAMING 固定不等式 | `test_lifecycle_pure.py` | 矩阵 S1（lifecycle stamp 三拍：preparing / dock 四合取 / active_run blocker） | gate 5b + 牙口（`test_check_gates_pure`） | 🟢 ｜ gatherer（DB 事实解析）无纯测试座，由矩阵真实 run 覆盖 ｜ run 活性/存在 = transport 事实、非 lifecycle 推导——三读者合法在册：ChatDock `runAttached` / `projects.$id.index` `hasRuns` / `runActive`；禁补戳读者 ｜ 「lifecycle 键恒在」：graph 响应零节点早退同带 lifecycle 键 |
| Material Readiness（pending/processing/failed 归并 + required-input） | lifecycle gatherer + Asset 状态机 | ADR-087 §2 | `test_lifecycle_pure.py` | 矩阵 S2（真字节素材全链） | — | 🟢 ｜ 素材处理态由 fixture 显式声明，worker 调度永不定义剧本语义 |
| Upload-on-birth（素材节点随 asset 行出生，幂等，`spec.asset_id` 寻回） | `app/pipeline/graph_fill.py` `stamp_asset_node` | ADR-087 §2 | `test_graph_wiring_pure.py` 边界型 | — | — | 🟢 |
| Confirmation Doctrine（呈现 + 制作意图 + 当前授权通道 + 费用守卫） | lifecycle + `chat/service.py` | ADR-087 / ADR-117 / ADR-139 | `test_lifecycle_pure.py` | 当前矩阵的 dock/typed Start 与付费边界旅程 | gate 5c（客户端不推导 readiness） | 🟢 ｜ auto 只免批准拍、不创造意图；ask 与守卫线仍确认 ｜ Charge 等价见 §3 |
| /generate Paid Authorization（approved retry 两级证明 exact/family + 不可证 → machine-readable `scope.unproven` 阻断，先于余额检查） | `app/pipeline/scope_classifier.py` + `routes/projects.py` 门 | ADR-087 §4 + Frozen Rule 9/10 | `test_scope_classifier_pure.py`（链分类矩阵 + family tier） | 矩阵 S9（typed Start 与 /generate 双路 422 同形同义 + 不可证载荷 `scope.unproven` + 台账零行） | — | ⚠️ ｜ targeted scopes（tasks=None）与 legacy slot-run 整类重做不可证在册（dock 路径覆盖；false negative = 安全向）｜ **approval provenance 仍待对账**：loader 目前纳入带 `context.tasks` 的历史 run，须验证无有效 confirmed/approved provenance 的 legacy run 不能授权，或明确重裁；生产暴露面未核实，见 lifecycle §0 |
| Start seat 服务端强制（`evaluate_start_gate` + 机器可读 blocker；dock Start、口头与 typed answer 同一机器） | `app/pipeline/lifecycle.py` + `chat/service.py` Start 分支 | ADR-087 §4 + ADR-117/139 | `test_lifecycle_pure.py` | 当前矩阵的活跃 run 阻断、合法 Start 与 422 旅程 | — | 🟢 ｜ 客户端只读服务端旗标，服务端阻断兜底竞态；Film 首稿 review hold 另有硬门 ｜ `pending_plan=True` 直传约束：answer 先写后 dispatch，门内读取不得复用旧戳 |
| `autonomy="review"` 退役（understand→plan 恒直通；interrupt 机器〔SuspendRun / resume / bail / expiry sweep / verify escalation〕保留） | `app/pipeline/orchestrator.py`（compile）+ interrupt 机器 | ADR-087 §4 | `test_decompile_pure.py`（无 direction interrupt 编译入图）；`test_scope_classifier_pure.py` autonomy fixtures（读容忍证明座） | 矩阵 S2（途中插话：提醒尾 + pending 保持 + 下轮回填） | — | 🟢 ｜ schema 读容忍：`StartAnswerRequest`/`ChatRequest.autonomy` accepted+IGNORED（`extra="forbid"` 下移除会 422 旧客户端）｜ run 执行权仲裁无自动化看护（ADR-114 知情放弃，Consequences 在案） |
| Charge Semantics | （合同层，无独立实现站） | ADR-063 | `test_lifecycle_pure.py::test_charge_semantics_ready_is_exactly_the_docked_plan` | — | — | 🟢 ｜ 当前 ≡ has_pending_plan（故意等价，§3） |
| Scope 分类（continuation/expansion/unproven + 链逐字 retry 证明 + 零 op 语义可扩展锁 + registry-known 即付费） | `app/pipeline/scope_classifier.py` + chat 提案出口 | ADR-087 §4 + ADR-117/139 | `test_scope_classifier_pure.py` | 当前矩阵的 continuation、expansion、授权与 422 旅程 | — | 🟢 ｜ continuation 可在既有授权内续跑；expansion 按 auto/ask 与制作意图分流；unproven 失败闭；/generate 不可证先于余额检查；gatherer 无纯测试座 |
| Activity 投影（白名单字段 / 用户语义 kind / seq 严增 / 翻转律 / N→1 repair 聚合 / 终态唯一） | `app/chat/activity.py` + routes 缝 | ADR-087 §3 | `test_activity_pure.py` | harness 公共断言（Activity 帧形态，矩阵每本自动携带） | gate 5a（内核侧反向） | 🟢 ｜ ActivityStream 渲染级（DOM）无单测——reducer / replay / stream dispatch 三套件在 vitest 层 |
| ToolLoop 内核边界（LoopEvent 只说 WHAT HAPPENED，无 Activity 构造词汇） | `app/agents/tool_loop.py` | ADR-087 §5 | `test_tool_loop_pure.py` + gate 5a 牙口 | — | gate 5a | 🟢 |
| Lifecycle/Presentation 依赖方向（lifecycle 禁 app.chat） | `app/pipeline/lifecycle.py` | ADR-087 §5 | gate 5b 牙口 | — | gate 5b | 🟢 |
| 客户端 lifecycle 读取纪律（读戳合法，本地生成 truth 非法） | `apps/web` ChatDock | ADR-087 §5 | gate 5c 牙口（正反探针） | — | gate 5c | 🟢 ｜ 禁的是「生成」，读 server projection 恒合法 |
| Import 方向（pipeline ↛ chat 任意深度零命中；跨顶层包私有名 import 清零；组合根双缝接线） | `app/pipeline/trigger_events.py` + `conversation_bridge.py` + `app/chat/seams.py` | ADR-087 §6 | `test_import_direction_pure.py`（AST 双门 + 冷导入双子进程探针 + 接线保险 + 同名局部碰撞扫描） | — | AST 门全树扫描（含 deferred）；组合根源码断言 | 🟢 ｜ 冷导入探针 = 验收主依据：pipeline 全模块新鲜解释器批量导入 `sys.modules` 零 `app.chat*`；反向 `app.chat.service` 冷导入合法落 pipeline（单向街）｜ app 树 only 扫描（scripts/tests 豁免）；组合根注册 = 唯一合法 pipeline→chat 缝 |
| 戳消费谓词三态（missing ≠ ready） | `apps/web/src/lib/lifecycleStamp.ts` | ADR-087 §2 | `lifecycleStamp.test.ts`（vitest） | — | gate 5c | 🟢 |
| Web 纯缝（activity reducer / replay 映射器 / stream dispatch） | `apps/web` activityReducer / historyReplay / chatStreamFrames | ADR-087 §1/§3 + 打字机律 | 三套件（vitest 纯 node 零 DOM） | — | — | 🟢 ｜ DOM 渲染级无单测（live-only） |
| Canvas / Chat Start 入口（画布不另建执行 chrome；dock Start、口头与 typed answer 共用服务端 gate） | `apps/web` flow/ + ChatDock + `chat/service.py` | ADR-111 / ADR-117 / ADR-139 | — | 当前矩阵的确认与 Start 旅程 | 退役的画布独立 Start 标识符清零（grep 可证） | 🟢 ｜ 画布 DOM 负向与真实口头路径仍需 live 验收；auto 无制作意图时必须安全挂起 |
| Product Graph（词表 v3 / apply_wiring_ops 唯一写口 / 读面映射） | `app/pipeline/graph_*` | ADR-057 / ADR-076 | `test_graph_wiring_pure.py` + `test_product_graph_pure.py` | 矩阵 S2（chat 修订 wiring 横切：同 id 原地改写无双生 → 子图重跑） | — | 🟢 |
| C-0/C-1/C-2 拓扑空间权威三律（membership / rank / RunOp 拓扑序） | `app/pipeline/product_graph.py` | ADR-086 | `test_product_graph_pure.py` | — | — | 🟢 ｜ legacy `materialize` 行的读面可见性与谓词不一致 = 已知残留；生产 DB 清零证据与删除条件归 本文 §5.3/§5.6 |
| Execution（fenced 零副作用 / SKIP LOCKED 认领 / 毒丸护栏 / run 执行权） | `app/pipeline/jobs.py` + worker | ADR-017 / ADR-039 | `test_execution_fencing_pure.py` / `test_poison_pill_pure.py` / `test_run_authority_pure.py` | 矩阵 S9（付费边界双路 422） | — | 🟢 ｜ 失败不扣费 / 孤儿 hold 回收无自动化看护（ADR-114 知情放弃，Consequences 在案） |
| 计费账本（hold→capture→release / 负余额语义） | `app/platform/billing` | ADR-055 | — | `scripts/reconcile_credits.py`（仪表层）+ 矩阵 S9（负余额 hold 必拒） | — | 🟢 |
| Prompt 面（当前注册探针与绝对阈值 / 枚举漂移） | `app/prompts/chat/` | ADR-071 T2 | `test_prompt_registry_consistency_pure.py`（registry ↔ prompt 枚举一致性） | `scripts/prompt_gate.py` | — | 🟢 ｜ I 探针改靶后仍需按读数校准，永不为放行回归调阈；Film 专属探针族仍缺 |
| 三通道分家（System Status / Activity / Conversation） | routes + ChatDock | ADR-087 §1 | `test_activity_pure.py`（投影器无 phase 面反向锁） | harness 公共断言（SSE/Activity 帧形态；相位文案永不锁） | gate 5a / 5c | 🟢 ｜ 永不建「相位帧 → lifecycle readiness」正向锁 |
| Agent Working Loop 修订回路 + 收官审计 + 记忆窄切（revise_plan / revise_selects / revise_output / run_review / 快照路由 / get_artifact + Past journeys + exemplar） | `app/pipeline/exploration_store.py` + `run_review.py` + `scope_compile.py` + `app/chat/perception` | ADR-088 §6~§8·§10 / ADR-089 §4·§6·§8 / ADR-117/139 | `test_revise_selects_pure.py` / `test_run_review_pure.py` / `test_memory_narrow_pure.py` + scope_compile / exploration_tools / perception 守卫 | 当前矩阵的探索与修订旅程 + 六段 live 走查 | — | 代码层已落；live 与 edit_graph 退役证明开放。交付是否有建议/下一步按 ADR-135/141 对账，不恢复旧 pills 断言 |
| Agent Tools 长程序修订与读面 | `chat/propose_turn.py` + perception `get_node` / pending-plan / run-history reads | 当前 Chat 工具合同 + Working Loop | 现有 tool/perception 纯守卫 | 当前注册矩阵 + live API/dev worker 复跑：长程序先 `get_node` 再改、distilled `specific_instruction` 保留用户范围、pending-plan 与 run-history 读数一致 | — | ⚠️ e2e 未运行；不得恢复退役剧本名或用静态代码审查替代 |
| 精确编辑四族与归档恢复 | `chat/propose_turn.py` + `operations/` + outputs read model | ADR-090/091 + VIDEO_EDITOR §11 | `test_edit_output_pure.py` / `test_edit_span_pure.py` | 真实 run 覆盖 remove_range、set_trim、set_caption_style、set_title、journal/undo、rerun/archive/restore、归档写 409；pin 非焦点目标 | — | ⚠️ 精确编辑的现有 live 证据需在当前 HEAD 复核；pin 强制覆盖的分歧分支只有纯件证据，尚需自然分歧 live 或明确只接受纯件层级；provider 方差与未复现异常不写成当前缺陷 |

## 3. Charge Semantics 等价登记（ADR-063 终读）

**当前实现下 `charge_semantics_ready ≡ has_pending_plan`——这是当前合同
空间中的故意等价，不是测试缺失。**

- ADR-063：estimate 可 deferred（NULL estimate = 诚实 Deferred 披露面），收费语义随 pending plan 的 dock 即已完整披露，**estimate 完整性不阻塞 PLAN_READY**；但 NULL 不可报价族与 `always_confirm_above` 仍按 ADR-117 触发独立费用确认，任何档不得绕过。
- 推论：`PLAN_READY=true ∧ charge_semantics_ready=false` 在当前产品实现中
  是**不可达状态**；四合取的 charge conjunct 不提供独立运行时分叉，其
  独立性由合同层保留（未来引入独立收费语义准备态时它才有牙）。
- 若未来要支持「Plan Ready + 费用语义未完整 + Canvas 可审阅 + Confirm
  disabled」：那是 **ADR-063 / ADR-087 的产品合同翻案**，不是普通 bug
  fix——先拍板再动代码，届时本条目与等价钉同批改写。
- 钉位：`test_lifecycle_pure.py::test_charge_semantics_ready_is_exactly_the_docked_plan`。

## 4. 未闭环验收与实现差异

本节只维护剩余检查、实现差异与证据要求；产品规则分别归 CHAT_ARCHITECTURE、BILLING 与现行 ADR。下面各项仍待运行/核对，不继承 §2 的绿色符号作为 live 通过证明。按改动运行相关 pytest、check_gates、prompt_gate、当前注册旅程矩阵与 web 测试/tsc/build；付费检查遵循既有预算授权。

### 4.1 选项唯一座位

Canonical：CHAT_ARCHITECTURE §8.5/§8.8，ADR-081/099/100/116。

- **实现差异待核对**：chat_intent_system.j2 的小写字母选项 ID 指令与 check_options_dock 的数字语法覆盖须按 ADR-081 对账；本次未修改 prompt/守卫，不能宣称已修复。
- ADR-099 只保留三种现行终态形态与 trigger-only provenance；四层架构、交互宪法、Speech Commit Protocol 与默认吸收边界继续有效。NAMING 的 suggestion_ref/source_state 与终态形态须收窄到 trigger，不恢复 answer+suggestions。
- prompt_gate I 以 browse→ask_user 为目标，先取实际读数再校准；建议/ask_user 发射率固定模型/参数/场景取基线，区分模型未提、未调用与应用丢弃，不降阈或放松剧本放行。路由劫持零容忍，substrate 取证方法归 PROGRESS 对应需求。
- 自动检查至少包含 test_suggestion_provenance_pure.py、trigger 点击→下一回合编译、stale trigger 的具名原因、数字 id 与 1–5 结构外界、历史 answer replay 安全。
- live：浏览问题产生可用 dock（推荐、×/pencil 退出、合法且不外露宣告的 default path）；能力问答/闲聊只产纯 answer；有效 suggestion trigger 可 dock/点选/解算；历史 answer 硬刷新只读散文，无建议卡和崩溃。run_completed 不作为建议来源，使用 run_failed/craft_decompiled。

### 4.2 授权、会话计量与配置

Canonical：CHAT_ARCHITECTURE §3.1，BILLING §6.5/§7，ADR-117/139；Film 首稿另按 ADR-144。

- 设置读写覆盖缺席/非法值/部分键/同会话生效，确认控件只在 Settings「助手」，composer/dock 不出现偏好开关。
- auto/ask × quote=0/正价 × 守卫线 × NULL × 有无制作意图：服务端矩阵与真实 Chat 各覆盖代表路径；dock Start、口头/typed answer 共用 gate，Film 首稿不得同回合开工，confirmed_via/scope 证明真实。
- 真实回合检查 conversation_usage：每回合一行，tokens/cache/cost/model/project 归属正确，多迭代聚合、无调用空回合零行、记录失败不打断回复；永不上用户账单/UI，不替代 agent_calls。
- context 窗口边界与世界状态幸存有纯覆盖；预算是否调整由真实 usage 分布决定，保持 prefix-cache 稳定顺序，滚动摘要不能代替溢出证据。
- 费用四面同源、NULL/守卫线文案诚实，积分余额/冻结/台账一致；工作段、Dock 两形态、打字机与信封权威不回退。
- 查询目标环境的 configs 旧 key billing.confirm_large_threshold，按已授权范围清理真实残留并记录执行状态；旧 confirm_strategy 不新增兼容语义。本次未查/改目标 DB，也未运行以上仪式链或 live 检查。

### 4.3 素材理解与对话回放

Canonical：CHAT_ARCHITECTURE §3.5/§8，ADR-102/113。

- prompt_gate、当前素材/咨询旅程矩阵、相关纯测试与 web 检查仍待完成；不恢复已删除的 material-wait 事故套件。
- live：① 寒暄/能力问答零 worker 事件与素材处理；② 视频提问出现真实 read-active，等待实际 ASR 后同回合 grounded answer/诚实失败；③ 同素材追问 digest 命中、零等待。
- ④ 硬刷新每条 opening/user message 恰好出现一次，不丢不重；⑤ 无素材读取问题的上传不产生处理活动或虚假叙事；⑥ 素材读取回合只有一个 read Activity 生命周期，回答有依据，不逐资产重复叙事。
- ⑦ ask_user 不可见/散文宣告 default-path，不复读内部法条；⑧ in-flight beat 被抑制时，无 in-flight 的合法 run-birth beat 仍可出现；⑨ read/plan 都没有独立 transcript 节点/卡，资产卡只反映真实状态。
- worker 停摆导致无限等待仍是登记风险；超时/取消/降级不在本整理批擅改。ASR GPU/云加速为独立运营评估，不作为本验收完成项。

## 5. 共享机制与 UI 的当前验收

这些检查尚未闭环，不继承旧批次完成状态。旧 task 的过程、固定事故项目与旧数据救援工单不再是新架构施工前置；仍需的行为合同在各母文档/ADR，下面只登记当下验收和未定事项。

### 5.1 Render ownership 与恢复

Canonical：RENDERING、ADR-096。静态 owner/屏障包含同 output 全部写者；非 owner 失败不得交付部分 spec，track 局部原子写和完整 ClipSpec 校验继续有效，reconcile 不替代正常 compiler/runner。

待验：owner/其他写者启动及完成的两种顺序、写者失败阻断、屏障等待中取消、run 恢复不重复执行、fork owner 只等自己的写者；并发不同 track 不丢更新、同 track 冲突有诊断、联合约束复校；空/缺文件、spec 版本失配、归档或跨 run 在飞渲染不误认领。真实 worker/live 与纯测试证据分开。

无实际用户环境不再要求恢复特定历史 dev 产物；该操作工单退出，不记“已恢复”，也不把一次性裸 SQL 修复推广为正常路径。

### 5.2 Product artifact 身份

Canonical：ADR-097、MODULE_ARCHITECTURE。work_key/artifact_key/artifact_name/artifact_role 与 fill_key 独立；is_product_node 与 role 分层，无 key 为 unknown；名称按 ADR-058 手改撤名。成员不能从 rank/邻接/时间戳/共享 output/fill_key 猜出，display lineage 不参与调度/stale 闭包。

待验：fresh 视频→金句短片只有真实目标交付卡与 companion，transcript 在资产卡；同 output 只属一张交付卡、fork 独立、archive 可追溯、每 artifact 至多一个 activity owner；改变 rank/边序等不改成员；transcript overlay 不因 display 边错误失效。readiness 术语须有真实事实。跨产物 product_artifact/artifact_version 表是 OPEN，不能与 Composition 同期默认建另一套作品层。

### 5.3 Product graph、staging 与可选 Canvas

Canonical：ADR-086/098/113、CHAT_ARCHITECTURE §5。fresh graph 禁 task_book/transcript/纯执行节点；rank 唯一，lineage/ctx 不参与 rank 与 RunOp，布局不能影响执行；effective/display 只读，settled-rank freeze、append-only 与 source→target reveal 顺序保留。

待验：多文件上传/真实进度/失败重试/删除/attach 阻塞、PUT 成功未 attach 的 TTL 回收且不删已引用 key；fresh 图资产/产物身份一致；恶意反向 frame 不改 RunOp 拓扑与隐藏 modifier 顺序；server display_ranks 与前端投影同 fixture 同数、单成员 cohort 无幽灵 corridor、并行 writer/新增成员不移动旧卡、素材删除 reflow 为具名后果；背景 refetch 不动相机。移动端纯 Chat、深浅主题与真实 Start 都要验证。

空 frame 出生保障、缺帧 dev 失败/prod rank 回退、按 rank reveal/reduced-motion、同族分组/长边/settled 居中仅为后续需求，不把旧 C-3/Batch D 当成新视频前置。禁止服务端逐节点 drip-feed、第二 rank 或为排线造语义节点。

### 5.4 素材卡、Transcript 与精确编辑边界

Canonical：ADR-113/115、UI_GUIDELINES、VIDEO_EDITOR。源 transcript/extracted_text 与 edited_transcript overlay 分开，words/timestamps 不可变；cues 只读派生；资产 GET/PUT transcript 零 run/积分，无 graph JSON 双写，不冒充 ASR 时间戳。

待验：StageSkin/视频轴/cue seek/cross-highlight 与真实源区间一致，overlay 时隐藏不可靠时间皮，恢复原文后回归；NLE_AXIS_PX=116 与镜像常数、26px modifier lane、port/handles 同步；不同旧尺寸与现有布局不溢出，深浅主题、medialess/粘贴资产诚实，L0 常驻/L1 HoverChip/L2 inspector 不藏结构。刷新后 overlay 与时间轴/锚一致。初始 fixture 的 48 cues/5:40 badge、2:59–3:45 clip 与六字幕块只是可替换的具体检视样例，不要求保留某个事故项目。

未实施：edited-transcript 驱动 re-cut、overlay 进入 Operation Model、粘贴估算词轴、drag-select、modifier-lane 内容面/port、竖屏折叠；无新批准不扩首批范围。

### 5.5 消息数组、Checkpoint 与 Candidate Surface

Canonical：CHAT_ARCHITECTURE §8、ADR-108/109/110。seq 可有间隙；首回合与 conversation 同事务分配，后续用独立计数器短事务。append 定位/update 原位，禁止时间戳重排；cancelled 留审计但不显示，failed 诚实告警，零 delta 走 settled/typewriter。

待裁决：candidates_log 聚合行是正式例外还是改细粒度行；不得默许豁免或为数组化破坏单卡 repaint。不增查询端点。覆盖 set/同集重发/selection/revise/失败/answer-turn 六类载荷的 live/replay 顺序、幂等/替换、selection 无空行、失败回滚与持久化一致、跨轮重选。event/sync 无 Activity 只作 parity 观察，不自动扩需求。

Checkpoint 五路承重覆盖：非终态非空散文合法参数且有 channel 时 post-validation/pre-execute 发射且 execute 不重复；终态仅 settled；参数拒收不发/不执行/不留残片；无 channel 最终 envelope 不丢不重；cap=4 后记 capped 且不把截散文回灌 ledger。保留 tool_loop_checkpoint/tool_loop_checkpoint_capped 读数，结构性单读零 checkpoint 合法，不追数量。

fresh 首/后续 conversation 分别检查 FK/seq、刷新切 tab、WorkSegment 与 failed/cancelled；保留历史的环境才要求活动旧行迁移及回放证明。无用户 reset 路径不需要迁移事故项目。

### 5.6 Lifecycle 与后续 hygiene

Canonical：ADR-087/089/117/139。待验 derived/reasons、PLAN_READY≠CONFIRMATION_READY、missing stamp=unknown、估价完整性非 PLAN_READY 前置；/generate 的历史 context.tasks 不得在无有效 confirmed/approved provenance 时充当授权，生产暴露尚未核实，需修实现或明确重裁。

scope 不可证保持 unproven；targeted tasks=None、legacy slot-run 安全 false negative 不强行放行。pipeline↛chat，trigger 白名单仅 run_completed/run_failed/craft_decompiled。旧 plan-card disclosure 按当前面清理并过 prompt_gate。旧 HOLD/相位退休记录不是当前证据，按 fresh 行为重验，不复做过时施工。

若删除 _read_face，先证明目标实例 generator/processor/agent/modifier/materialize 及旧 toolset 无消费者/存量；允许本轮授权 reset 后查零，不伪造迁移或已执行。已应用 Alembic 历史保留；无用户旧数据不再要求兼容搬运，仍保留数据的其他环境须先读容忍再收窄，不得混用授权范围。

后续 hygiene 不入关键路径：按职责拆 chat/service、models/schemas、graph_fill；Message.intent union；edit_output 事务对称性（失败零残留或明确 ADR 例外）；ChatDock 仅按依赖需要评估。逐缝小提交、行为不变，compile/import/依赖门与受影响旅程验证，不能损坏草稿保活、SSE、授权与唯一写口。

### 5.7 现有 UI 自足与锚卡

Canonical：UI_GUIDELINES、CHAT_ARCHITECTURE、ADR-118/122/143。待验移动纯 Chat 上传→授权→生成→delivered/partial/failed→修订；unknown 能力、无 world、pending plan、缺/重复 output_refs、失败不出假锚卡。桌面 auto/chat 切换按当前渲染能力，不钉历史设备；锚卡只是收据投影，N 个平铺/稳定去重，无新订阅、合集卡或第二 live 状态源。

真实 MediaLightbox 播放、跨 Home/Lightbox 声音互斥、离屏暂停所有权、copy/免责声明、双主题/无横溢、MentionEditor 不 remount、背景相机不动、WorkSegment 正确收口都未自动通过。交付正文始终只讲实际结果，不给界面引导或内部 ID。Home 真片状态只读 home-creation-entry-refresh；空货架/假 Queue/mic/反馈按钮不复活。

## 6. 后续验证仪器归位（PLANNED，非当前前置）

未来可把现有 live 验证移到 apps/api/harness（README、scenarios/core+按旅程拆分、prompt_gate、长期 probes），apps/api/tests 与 web 测试位置不变；scripts 只留运维/demo。先核对当前 app.* import 引导，保持注册表、阈值、断言与行为不变、零 schema/新依赖；只搬活跃仪器，fixture/worker/进程/配额/round-robin 按 §1。

实施时同批全仓更新命令/引用、不留复制件或第二注册表；以 collect/import 冒烟、受影响 pytest/check_gates/web 检查验证，付费全量仍按授权。本文已作为验证母文档启用，不代表 harness 代码已经搬迁；当前 scripts/chat_scenarios.py 与 scripts/prompt_gate.py 路径继续有效。
