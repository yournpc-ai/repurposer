# Verification Contracts — Registry

> Phase 2.5（Verification Contract Migration）收口批（Batch C, 2026-09-19）产物。
> Tests / Scripts / Harness = 当前 Architecture Contract + Product Contract 的
> executable specification；本文档是验证侧的单一事实源：合同登记表、Known
> Variance 登记、fixture 律、以及与初始审计（锚点 `3236fae`）的 final diff。
>
> Status: **ACTIVE（Batch C 收口落档）**。产品/架构合同变更时同批更新本表。

## 1. 验证哲学（三原则）

1. **Tests protect contracts, not historical implementations.** 测试锁的是
   合同，不是某个历史实现形态；实现替换时测试按合同重审，不按代码怀旧。
2. **Contract migration requires intentional product/architecture change.**
   测试迁移的唯一合法理由是合同被有意变更（有 ADR / 用户拍板）；**永不**
   为了让当前实现变绿而削弱断言。「base 同样失败」不自动等于「测试该留
   失败」，也不自动等于「测试该删」——先裁决合同，再动测试。
3. **Scenario fixtures must explicitly establish the state under test.**
   剧本前置条件由 fixture 显式声明，background worker 的 timing / race
   永不定义剧本语义（实施细则见 §5 fixture 律）。

## 2. 合同登记表

| Contract | Owner | Canonical source | Pure tests | Scenario / script 座 | Static guards | Status / Known limitations |
|:---|:---|:---|:---|:---|:---|:---|
| Lifecycle 谓词（五态 + 四合取 + blocker 谓词序） | `app/pipeline/lifecycle.py` | ADR-087 §2 + NAMING 固定不等式 | `test_lifecycle_pure.py`（22） | S1 戳三拍（preparing/dock 四合取/active_run blocker）；S20A 戳断言 | gate 5b + teeth | 🟢 ｜ gatherer（DB 事实解析）只有剧本座，无纯测试 ｜ run 活性/存在 = transport 事实，非 lifecycle 推导（Phase 3 Batch C 拍板 B）——三读者合法在册：ChatDock `runAttached`（裁定 1 窗口收敛腿）/ `projects.$id.index` `hasRuns` / `runActive`；禁补戳读者（不重开信封→盖章窗口）｜「lifecycle 键恒在」不变量（拍板 A）：graph 响应零节点早退同带 lifecycle 键（空项目 blocked vs unknown 今日 UI 零差异） |
| Material Readiness（pending/processing/failed 归并 + required-input） | lifecycle gatherer + Asset 状态机 | ADR-087 §2 | 同上 T1–T6b | S20A / S20B + fixture 律（§5） | — | 🟢 |
| Upload-on-birth（text-yielding → transcript node queued 出生 + 幂等；非产出族不生） | `app/pipeline/graph_fill.py` `stamp_transcript_node` | Phase 1（8972e74 有意变更）+ ADR-087 §2 | `test_graph_wiring_pure.py` 边界型（四文本产出族阳性 + IMAGE/VOICE_SAMPLE/SLIDES 阴性 + 幂等） | — | — | 🟢 |
| Confirmation Doctrine（四合取组合点唯一 + 手势必需 + dock pill 唯一座） | lifecycle + `chat/service.py` | ADR-063 / ADR-054 / ADR-070 | T9/T9b/T10/T10b/T15 + Charge 等价钉 | S1 戳拍②③；S13 422 出生地 | gate 5c（客户端不推导 readiness） | 🟢 ｜ Charge 等价见 §3 |
| Charge Semantics | （合同层，无独立实现站） | ADR-063 | `test_charge_semantics_ready_is_exactly_the_docked_plan` | — | — | 🟢 ｜ **当前 ≡ has_pending_plan（故意等价，§3）** |
| Activity 投影（白名单五键 / N→1 repair 聚合 / 1→0 过滤 / T16-A·B 终态） | `app/chat/activity.py` + routes 缝 | ADR-087 §3 | `test_activity_pure.py`（22，含路由缝 stub ×2） | `check_activity_shape` 接线 S6f / S10 / S20A / S20B / S21 | gate 5a（内核侧反向） | 🟢 ｜ 客户端累积/渲染零单测——ChatDock 静态证明 only（§6 DEFERRED）；strict co-fire 律随 Batch B ⑥ 退役（相位侧信号已删，协同失去对象） |
| ToolLoop 内核边界（U1：LoopEvent 无 Activity 词汇） | `app/agents/tool_loop.py` | 用户裁定 U1 + ADR-087 §5 | tool_loop 纯套件 + 5a teeth | — | gate 5a | 🟢 |
| Lifecycle/Presentation 依赖方向（lifecycle 禁 app.chat） | `app/pipeline/lifecycle.py` | ADR-087 §5 | 5b teeth | — | gate 5b | 🟢 |
| 客户端 lifecycle 读取纪律（读戳合法，本地生成 truth 非法） | `apps/web` ChatDock | ADR-087 §5 | 5c teeth（正反 8 探针） | — | gate 5c | 🟢 ｜ 禁的是「生成」，读 server projection 恒合法 |
| 戳消费谓词三态（missing ≠ ready，判词 2） | `apps/web/src/lib/lifecycleStamp.ts` | ADR-087 §2 + Phase 3 判词 2 | `lifecycleStamp.test.ts`（10） | — | gate 5c | 🟢（Phase 3 Batch A） |
| Web 纯缝（activity reducer 对 / replay 映射器 / stream dispatch） | `apps/web` activityReducer / historyReplay / chatStreamFrames | ADR-087 §1/§3 + 打字机律 | 三套件（8/14/10，vitest 纯 node） | — | — | 🟢（Phase 3 Batch A）｜ DOM 渲染级仍 DEFERRED（§6） |
| Canvas 唯一确认座（Confirm/Start 唯 dock pill） | `apps/web` flow/ + ChatDock | ADR-070 + Phase 3 判词 1 | — | S1 戳拍②③（dock pill 路径） | draftConfirm/onDraftConfirm/startPendingPlan 标识符清零（grep 可证） | 🟢（Phase 3 Batch A）｜ 渲染级负向锁（画布无 Start 钮的 DOM 断言）仍 DEFERRED |
| Product Graph（词表 v3 / apply_wiring_ops 唯一写口 / 读面映射） | `app/pipeline/graph_*` | ADR-057 / ADR-076 | `test_graph_wiring_pure.py` + `test_product_graph_pure.py` | S12 等 | check_gates 既有门 | 🟢 |
| C-0/C-1/C-2 拓扑空间权威三律（membership / rank / RunOp 拓扑序） | `app/pipeline/product_graph.py` | ADR-086 | `test_product_graph_pure.py` | — | — | 🟢 ｜ legacy `materialize` 读面不一致 = 合同 §12 D-PFA-01 在册 |
| Execution（fenced 零副作用 / SKIP LOCKED 认领 / 毒丸护栏） | `app/pipeline/jobs.py` + worker | R1 批（I-EXEC-01~04） | — | S13 / S14 / S15 | — | 🟢 |
| 计费账本（hold→capture→release / 负余额语义） | `app/platform/billing` | ADR-055 | — | `reconcile_credits` + S13–S15 | — | 🟢 |
| Prompt 面（三探针绝对阈值 / 枚举漂移） | `app/prompts/chat/` | ADR-071 T2 | 枚举漂移 guard ×3 | `scripts/prompt_gate.py` | — | 🟢 ｜ `router_ab_probe` 移植挂账（§6 DEFERRED） |
| 三通道分家（System Status / Activity / Conversation） | routes + ChatDock | ADR-087 §1 | T14 反向锁（投影器无 phase 面） | — | gate 5a / 5c | 🟢 ｜ Phase 3 Batch B 解清：旧相位 token 全退役（③ 三替身 / ⑤ creating_run，§6），composing = System Status 唯一幸存叙事（判词 3），永不建「相位帧 → lifecycle readiness」正向锁 |

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
- 钉位：`test_lifecycle_pure.py::test_charge_semantics_ready_is_exactly_the_docked_plan`
  （B-1，`e0a2c9d`）。

## 4. Known Variance Registry

四态：**FIXED**（已消灭，不再占方差名额）/ **KNOWN VARIANCE**（确认的
LLM 行为方差，容忍）/ **KNOWN VERIFICATION FRAGILITY**（合同已兑现但断言
形态脆，挂账）/ **UNPROVEN**（未定性，待取证）。已解决的 fixture race
**永不**留在 Known Variance。

### FIXED（fixture / harness 层已消灭）

| 项 | 原类别 | 消灭于 |
|:---|:---|:---|
| S5/S7/S10/S20A 种子 PENDING + 虚构字节被常驻 worker 404→FAILED 的 E 类竞态 | E | B-4 deterministic fixture（`38883c1`，§5 fixture 律） |
| `terminal_tool_of` 把「settle 追问 + dock 计划同拍」误分 answer 轮 | C（harness） | Batch A（`8f84227`）：判别式 = dock 自身 answer 态 |
| gate 4 `checkpoint` 裸词禁咬 ADR-085 合法 reclaim（27 处） | harness 死架构假设 | Batch A：收窄为 `kind="checkpoint"` 上下文禁 |
| `PROCESS_NARRATION` 裸 `I'?ll` 在 IGNORECASE 下吞 "w**ill** pull"（S20A 两连红：「the caption text will pull from…」是诚实披露非过程泄漏） | harness 正则过火（合同不变） | C-6 裁决：补 `\b` 词界，正反探针双向实证 |
| S10 ask 轮套用单轮等式流式律 | harness 合同错误（C 类） | C-6 裁决：ask 三分解剖（`_ask_content`）下 options ask 的 content = 流式 framing、TEXT ask = framing + "\n\n" + bare question（compose 并入，永不流式）——等式对 TEXT ask 结构性为假，两连红的根因；改按分支断言，生产码零改动（2026-09-08 起未变） |
| `test_transcript_node_skips_textless_assets`（旧合同锁「无文本=无节点」） | 合同已翻案 | Gate 4A 裁决：8972e74 有意变更 → 迁移为出生合同测试 |
| `test_bare_question_follows_the_speech_language`（锁大小写实现细节） | 笔误红 | Gate 4B 裁决：语言正确 → 语义断言 |

### KNOWN VARIANCE（D 类 LLM 方差，容忍，复跑即绿）

| 剧本 | 方差面 |
|:---|:---|
| S1 | turn2 路由判定（draft vs settle ask） |
| S7-C | refinement 轮路由抖动：失败时 detail 恒 falsy = 修订轮后 pending plan 缺席（router 未 re-dock）；通过/失败交替（4 跑 2 绿），非确定性继承缺陷 |
| S10 | answer/draft 判定（few-shot 逐字镜像缓解，构造性方差；draft 拍单发一次散文口头确认代替 dock——当日 1/6）；ask 轮 preview `default_path` 空单发一次（prompt 合规抖动，未复现） |
| S20B | grounded-judgment 内容词 any-of：措辞自由下存在词表外措辞的非零概率 |
| S6f / S11 | 路由判定抖动（重试预算已在剧本内） |
| S5 | refine 轮 slots 抖动：无关 refine 偶发改写面板钉住的参数（2026-09-20 Batch B ⑧ 首跑单发，复跑即绿；合并座 `merge_prior_slots` 本批零触碰，harness 走裸 API 与客户端改动无涉） |

### KNOWN VERIFICATION FRAGILITY（挂账，不修生产码）

| 项 | 说明 |
|:---|:---|
| S20A `PROCESSING_DISCLOSURE` 正则语序洞 | 合同 = 披露语义存在（duty-bound clause），不锁措辞（禁令 #7）；正则宽容形状集不含「Processing is still underway」类语序 → 合同兑现但断言单发红。后续若要消除，扩正则宽容集（测试侧），**不动生产码** |

### UNPROVEN / 待定性

（当前无。原「相位帧正向锁缺失」一项已裁决结案——Phase 3 判词 3
（2026-09-20）：永不建「相位帧仍在发」的正向锁；相位整族随 Batch B
退役后对象消失，composing 保留为 System Status 宏观叙事，永不作
lifecycle readiness 之锁。）

## 5. 剧本 fixture 律（Batch B-4，强制）

**每个 Scenario 必须显式声明被测资产（fixture）的 processing / material /
failure state；测试前置条件永不由 background worker 的 timing / race 决定。**

机理：`seed_asset` 的默认态是 `PENDING` + 虚构 `scenario/*` 字节——常驻
worker 的 `claim_pending_asset`（只认领 `PENDING`，`FOR UPDATE SKIP LOCKED`）
会认领它、HeadObject 404、把行翻成 `FAILED`。剧本跑到一半，LLM 的 ground
truth 从「处理中」变成「处理失败」——前置条件被 worker 调度决定，断言沦为
轮盘赌。

合法的声明形态（按被测意图选，互斥）：

| 被测意图 | 声明 | worker 行为 |
|:---|:---|:---|
| 素材已就绪（内容与语言事实在场） | `processed=True` + `extracted_text` + `meta={"language": …}`（S20B 形） | 从不认领（COMPLETED 不可认领） |
| 素材未就绪 | `status=AssetStatus.PROCESSING`（S20A 形） | 从不认领（只认领 PENDING）；lifecycle 归并入 `material_pending` |
| 处理失败 | `status=AssetStatus.FAILED`（S16-P2 形） | 从不认领；lifecycle 读 `material_failed` |
| 真实处理（字节真实存在） | `file_url=<真实 bucket key>` + 默认 PENDING（S16 形） | 认领并真处理——此时 race 本身就是被测对象 |

禁止：默认值裸奔（不声明任何态的 `seed_asset(...)`）。fixture intent 必须
独立于 worker scheduling。

已硬化：S5 / S7(A/B/C) / S10 / S20A。S16 的 PENDING 是「真实处理」行的
合法实例（字节真实存在）。迁移中对齐此律的历史剧本在改动时顺手登记于此。

## 6. Final Inventory Diff（vs 初始审计，锚点 `3236fae`）

### KEEP（未动，合同仍有效）

- 纯 pytest 全套件（295 例基线全 KEEP，零 DELETE 候选的审计结论成立）
- S1–S21 全部剧本；prompt_gate；check_gates 既有门；vitest ×2
- accept_* / reconcile_credits / verify_beat_map / crop_track_parity / run_anatomy

### MIGRATED（合同仍有效，验证方式对齐 ADR-087）

| 项 | 迁移内容 | 批次 |
|:---|:---|:---|
| `check_stream_law` / `check_read_silent_stream` | had_reads/had_repair 改以 Activity 帧为主证（`_work_evidence` strict co-fire：System Status 报工作而 Activity 静默 = 红；`SCENARIO_ACTIVITY_LEGACY=1` 才降级计数 warning） | A |
| S6f | read 发生性断言 → assistant.activity（kind=read + activity_key） | A |
| S21 `_stream_reads` | Activity-first，phase 帧降为 print-only legacy fallback | A |
| S20A | fixture 钉 PROCESSING + 戳断言收紧为精确 `material_pending` | B-4 |
| S1 | 增 lifecycle stamp 三拍（preparing → dock 四合取 → active_run blocker + settle 归还） | A |
| gate 4 checkpoint 条款 | 裸词禁 → `kind="checkpoint"` 上下文禁（ adjudication 样例） | A |

### ADDED（新架构合同的新验证座）

| 项 | 批次 |
|:---|:---|
| gate 5a（内核禁 Activity 构造词汇 / 禁 Presentation·Domain import）+ 5b（lifecycle 禁 app.chat）+ 5c（客户端禁本地 readiness 推导） | A |
| `check_activity_shape` stable-identity 律（首帧出生 / kind 恒定 / 恰好一终帧 / 过去态 key 律） | A |
| S20B / S21×3 / S6f 接线 `check_activity_shape` | A |
| B-1：Charge 等价钉 + 多 blocker 谓词序钉（`test_lifecycle_pure` 20→22） | B-1 |
| B-2：上传即出生全边界型（`test_graph_wiring_pure`） | B-2 |
| B-3：`_sweep_activities` 路由缝 stub ×2（T16-B 服务端缝脱离剧本可证） | B-3 |
| B-5：gate 5a/5b/5c 牙口正反探针（`test_check_gates_pure.py`，5 例） | B-5 |
| 本文档（Registry + 哲学 + fixture 律 + 方差登记 + 本 diff） | C |

### DEFERRED → Phase 3（Presentation Migration / 相位退役联动）

| 项 | 位置 | 说明 |
|:---|:---|:---|
| ~~S10 drafting 相位断言~~ | `chat_scenarios.py` | **RESOLVED（Phase 3 Batch B ⑥, `37e252c`）**：相位通道退役后随葬——draft Activity 断言（present_plan name-known 生→收）是唯一座位 |
| ~~`_stream_reads` legacy print fallback~~ | `chat_scenarios.py` | **RESOLVED（Phase 3 Batch B ⑥, `37e252c`）**：纯 Activity 键序，print fallback 删除 |
| ~~`SCENARIO_ACTIVITY_LEGACY=1` 降级通道~~ | `chat_scenarios.py` | **RESOLVED（Phase 3 Batch B ⑥, `37e252c`）**：逃生舱 + 尾部汇总打印同删——第二信号消失后降级失去对象 |
| ~~旧 phase token（drafting/inspecting/repairing/creating_run）去留~~ | 服务端 + 客户端 | **RESOLVED（Phase 3 Batch B）**：③ 三替身退役（`44b5d4d`——工作证据归 Activity 投影器座位，inspecting i18n 族随读帧保留）；⑤ creating_run 删除（`b9dc6ee`——B4 CDP 死窗取证双场景 PASS 后剪线，`scratch/phase3_b4_deadwindow.mjs`）；composing 幸存为 System Status 唯一宏观叙事（判词 3） |
| ~~客户端 ActivityStream 渲染级 vitest + ChatDock reducer 纯化提取~~ | `apps/web` | **reducer 纯化提取已落地（Phase 3 Batch A，2026-09-19）**：`activityReducer.ts`（upsert/sweep/reset 纯函数 + 8 例）/ `historyReplay.ts`（mapHistoryRows + 14 例，含「恢复不推导 lifecycle」keys 白名单锁）/ `chatStreamFrames.ts`（routeStreamFrame + 10 例）/ `lifecycleStamp.ts`（戳消费三态谓词 + 10 例，missing ≠ ready）+ `vitest.config.ts`（纯 node 零 DOM，app 插件在 vitest 下挂起的 setup gap 已补）。**仍 DEFERRED**：ActivityStream 渲染级（DOM）vitest |

### DEFERRED → ops 卫生批（非本阶段）

- `dev.sh` 死旗 `DEMO_SEED_ASYNC` 删除（零读者，与 `SKIP_DEMO_SEED` 同族）
- `scratch/router_ab_probe.py` 移植到 ToolLoopAgent 接口（import 已断；prompt_gate 失败协议点名它做 A/B bisect）
- 一次性脚本归档判定（`migrate_to_tos.py` / `backfill_graph.py`）
- S11 `bilingual is True` → truthiness 断言迁移 + 产品侧 params coercion 挂账（B/D 边界，审计 §5 已裁）

### KNOWN VARIANCE

见 §4（LLM 方差族在册；已 FIXED 者不再占额）。
