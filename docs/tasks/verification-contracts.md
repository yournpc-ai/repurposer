# Verification Contracts — 合同 ↔ 承重守卫映射

> 验证侧单一事实源：产品/架构合同登记表。每行 = 一份合同：owner /
> canonical source / 守它的纯测试、剧本座、静态门。合同变更时同批更新本表。
>
> 测试资产哲学与分层（两类保留 / 部署前仪式链 / 仪表层）归 CLAUDE.md
> Testing；fixture 纪律与 LLM 方差处置归 `docs/tasks/test-suite-convergence.md`
> §3.6 / §5；剧本矩阵的形态断言纪律与 harness 公共断言归
> `apps/api/scripts/chat_scenarios.py` 头部。
>
> Status: **ACTIVE**。产品/架构合同变更时同批更新本表。

## 1. 验证哲学（三原则）

1. **Tests protect contracts, not historical implementations.** 测试锁的是
   合同，不是某个历史实现形态；实现替换时测试按合同重审，不按代码怀旧。
2. **Contract migration requires intentional product/architecture change.**
   测试迁移的唯一合法理由是合同被有意变更（有 ADR / 用户拍板）；**永不**
   为了让当前实现变绿而削弱断言。「base 同样失败」不自动等于「测试该留
   失败」，也不自动等于「测试该删」——先裁决合同，再动测试。
3. **Scenario fixtures must explicitly establish the state under test.**
   剧本前置条件由 fixture 显式声明，background worker 的 timing / race
   永不定义剧本语义（fixture 纪律见 `docs/tasks/test-suite-convergence.md`
   §5 与 `chat_scenarios.py` 头部）。

## 2. 合同 ↔ 承重守卫映射

剧本座列的「矩阵 S1–S10」= `apps/api/scripts/chat_scenarios.py` 用户旅程
矩阵（ADR-114）；「harness 公共断言」= 矩阵每本自动携带的 SSE 线格式 /
Activity 帧形态 / dock 形态 / 估价三断言。

| Contract | Owner | Canonical source | Pure tests | Scenario / script 座 | Static guards | Status / Known limitations |
|:---|:---|:---|:---|:---|:---|:---|
| Lifecycle 谓词（五态 + 四合取 + blocker 谓词序） | `app/pipeline/lifecycle.py` | ADR-087 §2 + NAMING 固定不等式 | `test_lifecycle_pure.py` | 矩阵 S1（lifecycle stamp 三拍：preparing / dock 四合取 / active_run blocker） | gate 5b + 牙口（`test_check_gates_pure`） | 🟢 ｜ gatherer（DB 事实解析）无纯测试座，由矩阵真实 run 覆盖 ｜ run 活性/存在 = transport 事实、非 lifecycle 推导——三读者合法在册：ChatDock `runAttached` / `projects.$id.index` `hasRuns` / `runActive`；禁补戳读者 ｜ 「lifecycle 键恒在」：graph 响应零节点早退同带 lifecycle 键 |
| Material Readiness（pending/processing/failed 归并 + required-input） | lifecycle gatherer + Asset 状态机 | ADR-087 §2 | `test_lifecycle_pure.py` | 矩阵 S2（真字节素材全链） | — | 🟢 ｜ 素材处理态由 fixture 显式声明，worker 调度永不定义剧本语义 |
| Upload-on-birth（素材节点随 asset 行出生，幂等，`spec.asset_id` 寻回） | `app/pipeline/graph_fill.py` `stamp_asset_node` | ADR-087 §2 | `test_graph_wiring_pure.py` 边界型 | — | — | 🟢 |
| Confirmation Doctrine（四合取组合点唯一 + 手势必需 + dock pill 唯一座） | lifecycle + `chat/service.py` | ADR-063 / ADR-054 / ADR-070 | `test_lifecycle_pure.py` | 矩阵 S1（dock pill 确认路径）；S9（422 出生地） | gate 5c（客户端不推导 readiness） | 🟢 ｜ Charge 等价见 §3 |
| /generate Paid Authorization（approved retry 两级证明 exact/family + 不可证 → machine-readable `scope.unproven` 阻断，先于余额检查） | `app/pipeline/scope_classifier.py` + `routes/projects.py` 门 | ADR-087 §4 + Frozen Rule 9/10 | `test_scope_classifier_pure.py`（链分类矩阵 + family tier） | 矩阵 S9（typed Start 与 /generate 双路 422 同形同义 + 不可证载荷 `scope.unproven` + 台账零行） | — | 🟢 ｜ targeted scopes（tasks=None）与 legacy slot-run 整类重做不可证在册（dock 路径覆盖；false negative = 安全向） |
| Start seat 服务端确认强制（`evaluate_start_gate` 评估序 + 五机器可读码 + 四合取戳阻断；dock pill 与散文确认同一座） | `app/pipeline/lifecycle.py`（纯核）+ `chat/service.py` Start 分支 | ADR-087 §4 | `test_lifecycle_pure.py` | 矩阵 S9（活跃 run → `start.blocked`）；S1（settle 后 Start 放行） | — | 🟢 ｜ 客户端读戳禁钮 = 第一道，服务端阻断 = 竞态兜底 ｜ `pending_plan=True` 直传约束：answer 先写后 dispatch，`is_pending_plan` 在门内恒 False——禁复用 |
| `autonomy="review"` 退役（understand→plan 恒直通；interrupt 机器〔SuspendRun / resume / bail / expiry sweep / verify escalation〕保留） | `app/pipeline/orchestrator.py`（compile）+ interrupt 机器 | ADR-087 §4 | `test_decompile_pure.py`（无 direction interrupt 编译入图）；`test_scope_classifier_pure.py` autonomy fixtures（读容忍证明座） | 矩阵 S2（途中插话：提醒尾 + pending 保持 + 下轮回填） | — | 🟢 ｜ schema 读容忍：`StartAnswerRequest`/`ChatRequest.autonomy` accepted+IGNORED（`extra="forbid"` 下移除会 422 旧客户端）｜ run 执行权仲裁无自动化看护（ADR-114 知情放弃，Consequences 在案） |
| Charge Semantics | （合同层，无独立实现站） | ADR-063 | `test_lifecycle_pure.py::test_charge_semantics_ready_is_exactly_the_docked_plan` | — | — | 🟢 ｜ 当前 ≡ has_pending_plan（故意等价，§3） |
| Scope 分类（continuation/expansion/unproven 三值 + 链逐字 retry 证明 + 零 op 语义可扩展锁 + registry-known 即付费） | `app/pipeline/scope_classifier.py` + `chat/propose_turn`（`_edit_graph` / `_propose_tasks` 出口 + `_dock_plan_as_question` 唯一 dock 座） | ADR-087 §4 + Frozen Rule 5/6/7/10 | `test_scope_classifier_pure.py` | 矩阵 S2（chat 修订 wiring 横切 = continuation；扩张 dock = expansion 确认门）；S4（caption_mode 随行翻转） | — | 🟢 ｜ continuation 自治 / expansion·unproven 回滚转 dock / propose 同 turn 永不生 run / /generate 两级 retry 证明；gatherer 无纯测试座 |
| Activity 投影（白名单字段 / 用户语义 kind / seq 严增 / 翻转律 / N→1 repair 聚合 / 终态唯一） | `app/chat/activity.py` + routes 缝 | ADR-087 §3 | `test_activity_pure.py` | harness 公共断言（Activity 帧形态，矩阵每本自动携带） | gate 5a（内核侧反向） | 🟢 ｜ ActivityStream 渲染级（DOM）无单测——reducer / replay / stream dispatch 三套件在 vitest 层 |
| ToolLoop 内核边界（LoopEvent 只说 WHAT HAPPENED，无 Activity 构造词汇） | `app/agents/tool_loop.py` | ADR-087 §5 | `test_tool_loop_pure.py` + gate 5a 牙口 | — | gate 5a | 🟢 |
| Lifecycle/Presentation 依赖方向（lifecycle 禁 app.chat） | `app/pipeline/lifecycle.py` | ADR-087 §5 | gate 5b 牙口 | — | gate 5b | 🟢 |
| 客户端 lifecycle 读取纪律（读戳合法，本地生成 truth 非法） | `apps/web` ChatDock | ADR-087 §5 | gate 5c 牙口（正反探针） | — | gate 5c | 🟢 ｜ 禁的是「生成」，读 server projection 恒合法 |
| Import 方向（pipeline ↛ chat 任意深度零命中；跨顶层包私有名 import 清零；组合根双缝接线） | `app/pipeline/trigger_events.py` + `conversation_bridge.py` + `app/chat/seams.py` | ADR-087 §6 | `test_import_direction_pure.py`（AST 双门 + 冷导入双子进程探针 + 接线保险 + 同名局部碰撞扫描） | — | AST 门全树扫描（含 deferred）；组合根源码断言 | 🟢 ｜ 冷导入探针 = 验收主依据：pipeline 全模块新鲜解释器批量导入 `sys.modules` 零 `app.chat*`；反向 `app.chat.service` 冷导入合法落 pipeline（单向街）｜ app 树 only 扫描（scripts/tests 豁免）；组合根注册 = 唯一合法 pipeline→chat 缝 |
| 戳消费谓词三态（missing ≠ ready） | `apps/web/src/lib/lifecycleStamp.ts` | ADR-087 §2 | `lifecycleStamp.test.ts`（vitest） | — | gate 5c | 🟢 |
| Web 纯缝（activity reducer / replay 映射器 / stream dispatch） | `apps/web` activityReducer / historyReplay / chatStreamFrames | ADR-087 §1/§3 + 打字机律 | 三套件（vitest 纯 node 零 DOM） | — | — | 🟢 ｜ DOM 渲染级无单测（live-only） |
| Canvas 唯一确认座（Confirm/Start 唯 dock pill） | `apps/web` flow/ + ChatDock | ADR-070 | — | 矩阵 S1（dock pill 路径） | draftConfirm / onDraftConfirm / startPendingPlan 标识符清零（grep 可证） | 🟢 ｜ 渲染级负向锁（画布无 Start 钮的 DOM 断言）live-only |
| Product Graph（词表 v3 / apply_wiring_ops 唯一写口 / 读面映射） | `app/pipeline/graph_*` | ADR-057 / ADR-076 | `test_graph_wiring_pure.py` + `test_product_graph_pure.py` | 矩阵 S2（chat 修订 wiring 横切：同 id 原地改写无双生 → 子图重跑） | — | 🟢 |
| C-0/C-1/C-2 拓扑空间权威三律（membership / rank / RunOp 拓扑序） | `app/pipeline/product_graph.py` | ADR-086 | `test_product_graph_pure.py` | — | — | 🟢 ｜ legacy `materialize` 行的读面可见性与谓词不一致 = 已知残留（合同 §12 D-PFA-01，随历史清理收编） |
| Execution（fenced 零副作用 / SKIP LOCKED 认领 / 毒丸护栏 / run 执行权） | `app/pipeline/jobs.py` + worker | ADR-017 / ADR-039 | `test_execution_fencing_pure.py` / `test_poison_pill_pure.py` / `test_run_authority_pure.py` | 矩阵 S9（付费边界双路 422） | — | 🟢 ｜ 失败不扣费 / 孤儿 hold 回收无自动化看护（ADR-114 知情放弃，Consequences 在案） |
| 计费账本（hold→capture→release / 负余额语义） | `app/platform/billing` | ADR-055 | — | `scripts/reconcile_credits.py`（仪表层）+ 矩阵 S9（负余额 hold 必拒） | — | 🟢 |
| Prompt 面（10 探针绝对阈值 / 枚举漂移） | `app/prompts/chat/` | ADR-071 T2 | `test_prompt_registry_consistency_pure.py`（registry ↔ prompt 枚举一致性） | `scripts/prompt_gate.py` | — | 🟢 ｜ I 探针阈值未校准——首次定带跑后按读数校准（校准跑归用户，永不为放行回归调阈） |
| 三通道分家（System Status / Activity / Conversation） | routes + ChatDock | ADR-087 §1 | `test_activity_pure.py`（投影器无 phase 面反向锁） | harness 公共断言（composing = System Status 唯一相位座） | gate 5a / 5c | 🟢 ｜ 永不建「相位帧 → lifecycle readiness」正向锁 |
| Agent Working Loop 修订回路 + 收官审计 + 记忆窄切（revise_plan / revise_selects 三金钱态 / revise_output craft 续跑·迷你包 / run_review 兑现清单 / 快照路由 / get_artifact + Past journeys + exemplar） | `app/pipeline/exploration_store.py` + `run_review.py` + `scope_compile.py`（route_revision / assemble_craft_revision）+ `app/chat/perception` | ADR-088 §6~§8·§10 / ADR-089 §4·§6·§8 | `test_revise_selects_pure.py` / `test_run_review_pure.py` / `test_memory_narrow_pure.py` + scope_compile / exploration_tools / perception 既有面漂 guard | 矩阵 S3（素材→建议→探索：探索三族出生 / 决策包 dock / confirmed_scope 快照 / 产物落地 + 确定性尾） | — | 🟢 |

## 3. Charge Semantics 等价登记（ADR-063 终读）

**当前实现下 `charge_semantics_ready ≡ has_pending_plan`——这是当前合同
空间中的故意等价，不是测试缺失。**

- ADR-063：estimate 可 deferred（NULL estimate = 诚实 Deferred 披露面），
  收费语义随 pending plan 的 dock 即已完整披露，**estimate 完整性永不阻塞
  Confirm**。
- 推论：`PLAN_READY=true ∧ charge_semantics_ready=false` 在当前产品实现中
  是**不可达状态**；四合取的 charge conjunct 不提供独立运行时分叉，其
  独立性由合同层保留（未来引入独立收费语义准备态时它才有牙）。
- 若未来要支持「Plan Ready + 费用语义未完整 + Canvas 可审阅 + Confirm
  disabled」：那是 **ADR-063 / ADR-087 的产品合同翻案**，不是普通 bug
  fix——先拍板再动代码，届时本条目与等价钉同批改写。
- 钉位：`test_lifecycle_pure.py::test_charge_semantics_ready_is_exactly_the_docked_plan`。
