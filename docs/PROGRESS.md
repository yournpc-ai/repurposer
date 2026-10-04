# PROGRESS — 进展、排期与需求池

> Status: 活跃快照（每周五滚动；周期结束归档时 §1/§2 随周期滚动，§2 末"需求池"三表为常驻节，带入下一周期；§0 当前里程碑区 = R1/R1.1 施工序列的唯一事实源，§1/§2 = 产品现状快照与远期框架）；Cycle 1 历史归档于 `archive/PROGRESS-2026-cycle1.md`
> 本文是**排期 / 优先级 / 需求池的唯一事实源**（未排期需求见 §2 末需求池）；其他文档只引用周次或需求池条目，不复述排期。双受众：内部管理 / 投资人可摘录。

## 0. 当前里程碑与施工序列

> 本节是**新会话的唯一入口**：本节 → 当前 batch 的施工合同 → 合同引用的架构文档 → current HEAD。§1 起为产品现状快照与远期排期框架；与本节冲突时**以本节为准**。

### 0.1 里程碑状态

- **R1 — Core Product Beta：✅ 已封板（2026-09-17）**——implementation complete, acceptance closed：四 invariant（I-EXEC-01~04）+ S17 族 + B2 §10.2–10.5 实弹竞态演练全绿。仍 OPEN（有界，不阻塞封板）：baseline LLM 方差族 S1 / S6f / S10（登记在案，非 release regression；follow-up probe 保持 OPEN）。R1 定义 / 批次完成记录 / DoD 全账归 `archive/PROGRESS-2026-cycle1.md`。
- **R1.1 — Commercial / Distribution：排期挂起**——随支付商对接节奏或更后再议；批次合同已备（§0.3），启动时日期周五滚动定。
- **Product Flow Alignment：施工中**——Upload Staging / 统一相位 / Product Graph 语义与 Layout / 画布出生编排四批 + E2E；架构地基 ADR-086（拓扑空间权威三律 + Product Canvas ≠ Execution Graph）；施工合同 `tasks/product-flow-alignment.md`（§0.2）。
- **Agent Interaction & Product Lifecycle Architecture：Phase 0 文档冻结完成**——Architecture Fitness Audit（等级 B——骨架正确、边界重划）的允许重划面落档为 **ADR-087**（五条原则 + Lifecycle / Activity / Confirmation 三合同 + 依赖方向）；施工 = Phase 1~6 六份简报（§0.2），阶段门禁：每 Phase 全闭环才进下一 Phase。与 Product Flow Alignment（验收中）并行，**C-0/C-1/C-2 保护合同不动**（一切 lifecycle/activity 改造只在 read-side，不进 graph write gate）。
- **Agent Working Loop & Exploration Artifacts：旅程四收敛（docs-only）**——Agent Tools 审计（`scratch/agent-tools-audit-2026-09-22.md`：A-1 程序盲改 / P0-① 批准出处缺席 / P0-② instruction 双哲学 / P0-③ 工具词表内部化实锤）→ 旅程四 11 拍模拟（JOURNEYS.md，发现型目标的 Agent 工作循环）收敛：北极星（Agent 主循环 = 生产/修订用户可理解的项目产物，Run = 受授权执行阶段）+ R1~R26 裁决台账落档为 **ADR-088（Exploration Artifacts & Project Working Loop）/ ADR-089（Capability Compilation & Execution Boundary）** + NAMING 探索产物词族（N-55）。施工 = **修复批先行**（A-1 `get_node` + specific_instruction 对账 + read 洞 + SSE 实流 CoT 审计）→ **ADR 实施批**（探索族 schema → 探索写门 + 终态工具族 → 编译器 + 决策包/快照 → 修订动词 → propose_tasks/edit_graph 并行→退役弧），排期周五滚动定；**实施批分三次迭代**——迭代一 = 探索产物族数据面 + 画布呈现（合同 `archive/tasks-done/agent-working-loop-iter-1.md`）；迭代二 = 编译器 + 决策包/Confirmed Scope Snapshot（销 P0-①）+ R6 发现型路由 + 主链 e2e 首通；迭代三 = 修订回路 + reviewer + 记忆读取律 + 迁移弧 + 终态对标验收；**验收 = 终态体感对标（唯一验收口径）**：**OriginCut 左栏体验全等映射**——多段第一人称工作叙事（工艺理由自然段）+ 散文段间穿插证据行（可展开 + 耗时）+ 收官摘要 + 确认只在付费边界（OriginCut 输入框同法："Agent 会与你确认后再实施"）；**右侧时间线永禁照抄**（L3 铁律不变，我们的右侧 = 画布产物图）；可执行检查表 = 六拍体感剧本（直接开干 / 过程可见 / 中途插话免费秒改 / 只在渲染前停一次 / 收官自检汇报 / 一句话修订零仪式），全部跑顺才算成——批次完成度不是验收。实施序 = 工程内部事务（切片优先降风险，不占治理面）；**既有合同零推翻**（确认教义 / scope classifier D4 / draft 图 / dock 唯一座 / trigger turn / 打字机律 / 拓扑铁律全部原样承重——拍 6/9 压力测试在 JOURNEYS 旅程四）。

### 0.2 Active batch

| Batch | 内容 | 状态 | 施工合同 |
|---|---|---|---|
| Docs Slimming B1+B2 | 文档历史物理隔离（B1 `e7bb212`）+ 本入口恢复（B2 `fde345e`）；B3+（ADR 瘦身 / 架构文档去重等）重新审计后再评估 | ✅ 完成（完成即停线） | `tasks/docs-slimming-b1-b2.md` |
| **Product Flow Alignment** | Upload Staging Session → 统一相位/readiness gate → Product Graph 语义模型 + Layout（拓扑空间权威三律）→ 画布出生编排 → E2E——root cause 清单 L1-L5；架构地基 = ADR-086；需求池「画布可读性②」随 Batch C 吸收。**Batch A（upload staging）+ Batch B（相位清除协议 I-PFA-06 定型 + readiness gate I-PFA-07）+ Batch C-0（Product Graph 契约模块 `app/pipeline/product_graph.py` + canonical fixture，只定义不碰布局）代码已落**；Batch B 验收 PASS WITH RUNTIME GAPS（P0 runtime checks 用户自跑）；**C-0 收口 = PASS WITH DEBT**（fixture 13/13 绿；F1/F2 消解规则随 C-1 开工落档，F3 ctx 漂移待裁决）；**C-1（rank 单一事实源接线）代码已落**——服务端 `GraphNode.rank` 上线（read-time projection）+ `layout.ts` settled 投影改吃 rank（depthOf 退出图画布路径）；**C-2（RunOp 执行序解耦）代码已落**——排序键 = (rank, id) 拓扑序永不读 layout.x，modifier 执行序经 ungated rank 保全。**验收口径 = Greenfield**（不做旧数据兼容验收；只验全新项目 → 上传 → Generate → Canvas → Revision 链路）——验收中，通过即 C-0/C-1/C-2 收口，C-3/D 是否动工由产品需求倒推裁决 | 施工中 | `tasks/product-flow-alignment.md` |

| **Agent Interaction & Product Lifecycle Architecture** | **Phase 0 ✅（docs-only）**：ADR-087 落档（五条原则 / Lifecycle 五态 + Charge Semantics Ready / Activity 十规则 / Confirmation Doctrine / 依赖方向）+ README 事实源表补行 + NAMING 词族注册与死行清理（过程脊 / 渲染单元 / 结果画布 runFlow 定义 / 焦点注入）+ INTENT_COVERAGE 标记 historical → **Phase 1 Lifecycle Projection**（服务端命名谓词，projection additive → dual-read → switch → remove；转写节点 loading 出生随批）→ Phase 2 Activity Projection（追加式活动流，hook 接缝 3 座，无持久化首版）→ Phase 3 Presentation Migration（_read_face / activity_key / THINKING_PHASE_* 归位 + 客户端零 lifecycle 推导）→ Phase 4 Confirmation Doctrine Unification（统一 Paid Authorization path）→ Phase 5 Dependency Cleanup（import 图单向，冷导入探针）→ Phase 6 Hygiene（巨文件拆分，永不进关键路径） | Phase 1 **已落地**：`pipeline/lifecycle.py` 纯核+装配器、results/graph 双响应携戳、转写节点上传即出生、客户端谓词切戳（旧推导归零）；未跑验证项在简报 Status 在册（compileall/tsc/剧本 = 用户自跑）。Phase 2 **步①~④ 已落地**：tool_loop typed `LoopEvent` 通道 + `chat/activity.py` 纯投影器 + `assistant.activity` SSE 帧 + dock `ActivityStream` 并行渲染（active 在位时 System Status 行让位）；**步⑤（相位面收窄为 System Status 纯基座）HOLD——过剧本 + 产品试用验证门禁后施工**。**Phase 2.5 Verification Contract Migration 已收口**：gate 5a/5b/5c 静态边界三门 + harness Activity-first 迁移 + 剧本 fixture 律消灭 worker 竞态 + `tasks/verification-contracts.md` Registry/Known Variance 落档——**Phase 2 VERIFICATION CLOSED**；步⑤ 与旧相位退役仍 HOLD → Phase 3 联动。**Phase 3 CLOSED**：Batch A = Canvas 确认座退役（Confirm/Start 唯 dock pill）+ fallback-to-true 站点全灭（lifecycleStamp 三态谓词 missing≠ready）+ Web 纯缝 contract tests；Batch B = confirm/running 退位给戳（`confirmActive` 派生谓词 `intentReady && isPlanReady(lifecycle) && !runAttached`，ChatDock `type Phase` 状态机整删）+ drafting/inspecting/repairing 替身退役（Activity 投影器唯一座位）+ creating_run 删除 + composing 幸存 System Status 唯一叙事、永不建相位正向锁；Batch C = 几何债清理 + `_read_face` DEFER 维持（删除扳机 = DB 守卫查询，prod 挂账）+ DENSITY 渲染断言退役 + render_superseded 入注册表 + `chat/system_status.py`（不开 presentation 包）+ lifecycle 键恒在 + run 活性 = transport 事实 + `chatProtocol.ts` 抽出。**Phase 4 CLOSED**：四项终裁——D1 `autonomy="review"` 退役（ADR-087 §4「无 review 档」；WAITING_HUMAN/interrupt/expiry sweep/verify escalation 基建保留）/ D2 /generate = SERVER-VERIFIABLE APPROVED RETRY / D3 Start 服务端确认强制 / D4 continuation/expansion 按结果付费执行范围判定 + Frozen Rule 1~10（Decision Ledger 见 task 简报）；落地要点：B1 `pipeline/scope_classifier.py` 确定性分类器（**零 op 词汇**——消费 wiring 门前后图 facts 纯比对，D4 结果 scope 律，新 op/节点族/工具对分类器不可见；`produces_outputs=False` 是 settle 簿记旗非免费标，付费标记 = registry-known 即付费）；B2 edit_graph 按分类器裁决（continuation 自治直跑 / expansion·unproven 回滚转 dock）；B3 propose_tasks 同 turn create_run 全路径禁止（`_dock_plan_as_question` 唯一 dock 座；计费耳语 `chargeNote(WithEstimate)` 双形态随行，BILLING §2.1 Held+Actualized 披露闭缝）；B4 prompt 合同修正（propose = dock 待确认、run 只在显式确认后出生；continuation 自治 / 新增付费工作转 dock）；B5 /generate server gate（链分类器两级证明：`exact_retry` 全链逐字 + `family_retry` 单条历史链非空有序子序列，跨链组合/重排/参数改动/空链全部不可证；不可证 → machine-readable 422 `scope.unproven`，先于余额检查，永不 create_run）；B6 Start 服务端四合取强制（`evaluate_start_gate` 纯核 + `answer_question` Start 分支接门，结构化守卫机器可读——422 `start.blocked` 携戳 blocker ids，「前端按钮 disabled」不再是唯一防线）；B7 review 档退役（`TaskSpec.autonomy` 整删、`StartAnswerRequest`/`ChatRequest.autonomy` 保留读容忍 accepted+IGNORED）；B8 剧本/验证/docs 收口 + 三项 doctrine 终裁生效：ADR-087 §4（`plan_prose` 合取删除，空散文 dock 可确认，确认 scope = 卡载荷）/ 触发回合落点复评 `is_pending_plan` 命中即整体静默 / material gatherer plan-scoped 收窄。**Phase 5 CLOSED**：四族机制——① `pipeline/trigger_events.py` 白名单事件缝（三 kind 冻结白名单，组合根 app.main/app.worker 双注册，fire-and-forget 未注册 = 静默降级）② `pipeline/conversation_bridge.py` 会话写四命令显式 protocol（同签名 delegate + 未注册 fail-loudly）③ `platform/conversation_context.py` 会话读四助手只读协议座（MODULE_ARCH §4 批准座）④ regenerate 端点迁 `chat/routes.py`（URL/语义不变）+ `build_context` 迁 `chat/context.py` + 私有→公共扶正，pipeline→chat 清零、跨模块私有 import 归零、零新增 deferred；**探针入库** `test_import_direction_pure.py`（AST 双门 + 冷导入双子进程 + 接线保险 + 改名碰撞扫描）。Phase 6 待动工 | `tasks/lifecycle-phase-1-lifecycle-projection.md` / `tasks/lifecycle-phase-2-activity-projection.md` / `tasks/lifecycle-phase-3-presentation-migration.md` / `tasks/lifecycle-phase-4-confirmation-doctrine.md` / `tasks/lifecycle-phase-5-dependency-cleanup.md` / `tasks/lifecycle-phase-6-hygiene.md` |
| **Agent Tools 修复批** | 审计 `scratch/agent-tools-audit-2026-09-22.md` 的两条代码级实锤 + 同族 read 洞（北极星「用户可见 Agent Loop + Canvas Artifact Model」的地基修复，只修不建）：**Fix 1（A-1 程序盲改）**——perception 族加 `get_node` 全文程序读（Graph 段 140 字截断 vs edit_graph「从当前程序合成」规则结构性矛盾；4000 字预算帽超帽诚实标注）+ chat_intent_system.j2 补「修订前先 get_node 读全文」；**Fix 2（P0-② specific_instruction 双哲学对账）**——`ProposeTasksArgs` 加 distilled-EXTRA 字段（对齐 plan 路合同），`propose_turn` 改读 params 字段、缺席兜底 `text or None` 保旧行为，合同措辞抽共享 partial `_specific_instruction.j2`，消费口（caption 回放 / Start）不动；**Stretch（§7 d/e）**——`get_pending_plan`（chat 路 docked 计划读）+ `list_runs`（run 历史读）同注册纪律落地。i18n en/zh 双写六键 | ✅ 完成（已落 main）；doctrine / classifier / loop / 图写口 / service·plan_turn·context 零 diff；e2e 剧本未跑（需 dev worker，用户复跑） | 审计 `scratch/agent-tools-audit-2026-09-22.md`（§3.1 / §2 / §7） |
| **Agent Working Loop 迭代一：探索产物族数据面 + 画布呈现** | ADR-088 §1~§5 地基（三次迭代之第一次，终态对标在迭代三）：journeys 表 + graph_nodes.journey_id（R24 归属）→ 探索三族 spec 形状（CandidateSet 合集 / Select 证据引用 / ContentPlan 产品语义，R1/R3/R7/R8/R9）→ 探索写门（R14 双门：savepoint + 证据校验 + 幂等；探索节点零边；执行写门拒收 exploration 族）→ I-EXPLORE-01 纯测试锁 → 证据 reads（search_transcript / get_segment 注册 perception，prompt_gate）→ 探索终态工具族（EXPLORATION_TOOLS，harness 级不接生产）→ 画布三族卡面（合集折叠 / 精选理由行 / 方案 draft 虚线，R18 不镜像 running）→ S-explore 剧本。**开工裁决（ADR-089 §8）**：select_clips 保留为执行工具（零探索退化形态唯一机制），编译器永不从 Content Plan 编译出 select_clips，退役随迁移弧收口再评 | ✅ 完成（落地 + 实测全绿，含 S23 LLM 三拍对活 API） | `archive/tasks-done/agent-working-loop-iter-1.md` |
| **Agent Working Loop 迭代二：能力编译层 + 决策包/快照 + R6 路由** | ADR-089 实施（三次迭代之第二次，终态对标在迭代三）：编译器（Content Plan → Execution Scope）+ 决策包 + Confirmed Scope Snapshot（销 P0-①）+ R6 发现型路由 + work session 活动键 + revise_plan → 主链 e2e 首通。**逐项拍板制**。**① clip 编译目标 = cut_segments 已落地**——params = segments(1..5)+asset_id?+aspect?，caption_mode/language **不进出生参数**（transform 语义各有能力续链）；runner = materialize_source 零 LLM 模板一般化；新注册表轴 `llm_visible`（N-56 compiler-only 公民首座）+ N-32 一类型一生产者收窄到提案空间 + node_for_output 硬化；PlanOutput 产品语义三缺口补齐（+aspect 词表 / +dub / caption_mode 收窄三值）+ 方案卡面展示；编译路径窄集成（producer 判定 output_type 声明化 / label 座位 node_cls 直读 / spec 携带 / prelude-free 出生）全部恒等守护既有链。**②~⑦ + §4.1 + §4.9 全量落地（词表先行 N-57）**——writer source_span / `scope_compile` 编译器 / 决策包 dock / Confirmed Scope Snapshot 销 P0-① / R6 发现型路由生产接线 / chat.explore.* 活动键族 / revise_plan / S-explore-2 剧本——R14 双门预检编译（不可编译包零写入拒回 loop）、决策包三面（plans 阅读层双座 stamp + 编译链证据可展开 + quote）、快照五字段（confirmation_id/confirmed_at/confirmed_via/plans/compiled_scope+quote）、生产投影终态律（candidates/selects 非终态一回合连续工作、propose_plans/revise_plan 终态 R15 停顿）、手改撤名让座律延及 plans 阅读层。前端：dock 计划卡阅读层（plans 在上 + tasks 证据折叠展开）+ ActivityStream count 透传 + i18n en/zh 双写（generationOverlay.planOutputs.* / chainEvidence / chat.explore.* 五键） | ✅ 完成（落地 + LLM 驱动面实测全绿：prompt_gate 四探针 + S-explore-2 live e2e 全链） | `tasks/agent-working-loop-iter-2.md` |

| **Agent Working Loop 迭代三：修订回路 + 收官审计 + 过程可见 + 记忆窄切 + 迁移弧收口** | ADR-088/089 实施（三次迭代之最后一次，终态对标验收在本批）：修订回路（revise_output craft 零仪式 / revise_plan post-run / revise_selects 三金钱态）+ R20 快照修订路由器（plan_task_map + mark_compiled/supersede 双态写者）+ 收官兑现审计（run_review 确定性事实 + 建议 pill；自治修 P2 不做）+ chat path 产品语义化（探索工具入 chat path + 发现型判定 parity + loop 预算 6→12）+ 记忆三窄切（get_artifact / 历史旅程摘要 / exemplar 事实行；R25 窄门砍出本批）+ 过程可见升级（活动帧 at/duration_ms + 散文×证据时刻穿插单流）+ 迁移弧（select_clips 裁决落档 ✅ S0 / edit_graph 退役证明）+ 六拍体感剧本终态验收 | **代码层收口（S0~S9 全落）**——**live 验收待用户**（本批只做代码层检查，门禁与 live 回归用户自跑）：prompt_gate 全量 + S-explore-3/4/5 确定性尾三座 + 受影响旧座 + 六拍逐拍走查，脚本 = `scratch/iter3-six-beat-walkthrough.md`；全顺后 = 简报归档 + edit_graph 退役小提交（施工单 = 简报 §4 S8 施工记录） | `tasks/agent-working-loop-iter-3.md` |
| **言语真值大迭代 · 批次一：结算机修复** | 两起同族真 bug（ADR-093；取证 = 项目 4dabbd98 确认拍重复段落 live-only + freeform 作答不结算）：**W1 信封对账补全**——answer-SSE 续聊结算缝（ChatDock 选项作答路径 ~3218-3300）补内容真值替换，sendChat `finalizePreview` 全 parity，一切 SSE 结算路径同一完整对账；**W7 freeform 作答走结算机**——QuestionDock「其他想法」提交改走 answer 端点 `FreeformAnswerRequest`（服务端 `schemas.py:255` 早有 freeform 一等变体；客户端 `handleFreeformAnswer` 误走 sendChat 致问题永不结算、dock 残留、agent 下回合催答），与点选同一结算机（answered_at 落定 / dock 退役 / 续聊散文），打序号作答保回归，preview 期走同款寄存。纯客户端修复，零 prompt 面 | ✅ 验收闭环（W1 093dc7a / W7 d0ece60 + review 修 507efe2；用户 live 验收通过 2026-09-29） | ADR-093 + 开工提示词批次一 |
| **言语真值大迭代 · 批次二：言语权与节拍归位** | **W2 起始句 = start_run 回合 LLM 言语权恢复**（ADR-093 §2）——废止「纯确认零散文」契约，speech BEFORE calling 适用于 start_run，开工句模型自己说并落库为普通 assistant 行；客户端 chrome（`generationOverlay.startingLine` + 合成 startLine 单元）整删，服务端模板同禁；Start pill 化为「确认生成」用户消息走同一 sendChat LLM 道（Workspace 合同 C8）同进 start_run 回合，零 LLM 开工道诚实缺席；**W8 素材节拍三寄存器归位**（ADR-095）——入库节拍日志格措辞（动宾 + 事实后缀，动词分叉保留）+ live now-line 工序化（processor stage 经 `asset.meta` 出口，零 schema；随工序说「转写/理解」真话；内部工序名永不上屏）+ run stepper 与节拍面词汇对齐同一工序词表 | ✅ 验收闭环（W2 62c1adf / W8 5641348；prompt_gate PASS + 用户 live 验收通过 2026-09-29） | ADR-093 / ADR-095 + 开工提示词批次二 |
| **言语真值大迭代 · 批次三：分镜呈现** | ADR-094（取证 = 访谈素材静默中央裁剪 + 能力误读第二实证「定机位做不到镜头跟人」——与 `resolve_mode` 真实分支相悖）：**W3 trigger 否决资格护栏**（beat ① 引号示例判句整删，FREE PHRASING 兑现；否决理由永不建立在已交付能力直接处理的素材性状上）；**W4 分镜呈现律**——interview/single 形态在场时分镜 = 活方向（想法/首读/提案说得出、可 dock）；**选定分镜方向后链必含 select_clips+reframe_clip（选择执行律）**；未指明 + 竖屏 → 组合进链或 ask_user framing choice；静默中央裁剪永禁；确定性静默补链已否决；**W5 菜单措辞升格**（先读 `reframe/procedure.py` 三分支真值，既不欠卖也不过卖）；**W6 剧本回归座**（访谈素材 → 选分镜 → 链含 reframe_clip + 成片 crop_track 确定性尾） | ✅ 验收闭环（W3+W4 0b211bb / W5 06d953d / W6 1988a1f S24 座；prompt_gate 11 探针 PASS + 用户 live 验收通过 2026-09-29） | ADR-094 + 开工提示词批次三 |

| **渲染所有权 + Product Artifact Ontology** | 一轮取证三连（画布黑卡 / 一问三节点 / 完工播报撒谎）的本体级根治：**批次 A（立即）** = D2-status defer 状态感知 + verify 三合取 + finalize reconcile；**批次 B** = D4 卡死产物条件流程恢复；**批次 C** = artifact 投影 Phase 1（编译 stamp canonical 四字段 + 两层门 + 单 activity owner，零 schema）；**批次 D（终态）** = 编译静态 render owner + 屏障 + defer 律整条删除；**批次 E** = track 原子写 + 合并重校验（与 D 同族分验）；**批次 F** = artifact 级 lineage 真边 + canonical projection（收窄并入 C）。架构母法 = **ADR-096（渲染所有权与就绪语义）/ ADR-097（Product Artifact Ontology）**；序 = A → B → C → D/E → F，D·E 同族分开验证 | **A/C ✅ 验收批已落；D/E 代码层收口（D 160cf4f / E d6366a4，纯测试 841+11 基线不动）——live 验收待用户**（D 七交错序列 + 并行链零死渲染零提前渲染，E 三律，复跑剧本见批次报告）；**B 挂账**（D4 恢复待窗口）；F 收窄并入 C | `tasks/render-ownership.md` / `tasks/artifact-ontology.md` |
| **画布拓扑时间一致性（Effective Product Graph + Settled Rank 冻结）** | 708px 死列走查（素材 → 转写稿 → 金句卡两列净距 124 vs 708）的组合缺陷根治——岛出生吃写时拓扑、rank 投影吃读时拓扑（A3 合成边入 rank），同一批节点两张 Product Graph：**B1** = A3 合成抽 `effective_rank_edges` 纯函数入 product_graph，写时摆位/岛出生与读面同吃一层（去重只看 rank 合法三元组，lineage 永不占位；无 transcript 特判，消费者兄弟组自成岛）；**B2** = Z 冻结律门守卫（rank 边 connect/disconnect 进非 draft 目标 → WiringRejected；7b 对账内嵌同谓词；draft→settled 不存在性两证明入 ADR-098 §2）；**B3** = legacy 混合岛读时归一（cohort 拆分 + seq 重定基 + corridor 全死，零迁移）；命名例外 = 素材删除幸存消费者受控 reflow（非 regression）。架构母法 = **ADR-098** | 代码层收口（B1 `7787ee4` / B2 `a4ee8ee` / B3 `042decd`；纯测试 862 绿 + 11 基线不动，web 双镜像 fixture 10 绿）——**live 验收待用户**（存量 /graph 载荷恒等回归、事故项目读时归一、Start 主链、素材删除 reflow；未跑验证项在简报 Status 在册） | `tasks/canvas-effective-topology.md` |
| **Agent 交互架构迁移（ADR-099）** | 四事故（schema 漏出 / 指令式收尾 / repair 自白 / 浏览问两级跳）的架构级根治——lane 职责混合 → 四层边界（World Truth / Decision / Speech / Code Guard）：**B** caption gate 拆除（`service.py:688/:828` + 双 turn 调用点，caption_mode 降默认参）→ **C·C+** 一个 release unit（交互宪法六条+准入闸 & 终态交互形态谱系：answer+suggestions 非承诺档 + 建议点选 provenance（source_state 定向 stale 校验 + suggestion_ref），唯一基线）→ **S** 新架构 golden suite（Legacy Regression × New Interaction Contract 两层，批E 度量前提）→ **D** trigger 车道收缩 + RANGE 分组叙述禁（语义角色探针 EN→ZH 优先）→ **E** 言语法三簇零假设删除（3 smoke → 8-12 → 定点重放交错）→ **G1** repair 修宪 + rejection 取证落库 → **G2** 言语提交协议一般化（DeferredFrames 全终态推广，状态机测试清单）。顺序承重：E 必在 C·C+ 与 S 后（谱系不就位删除探针度量被污染）；B 合并后才动 C·C+/G（同触三文件）；三轮外部评审采纳/顶回记录入 ADR-099 | 迭代一（B/C·C+/S）已收口——验收已跑：S-core 9/9 绿、gate 11 探针全绿、legacy 9 红归因在册（既有债四族另开批）；迭代二（D/E）开工，批 D 首件 = C·C+ 账判软修（clips 类点名工作两见散文 narrate 不 dock，措辞强化句修）；G 未动工 | `tasks/interaction-architecture.md` |

**下一批**：本轮收口后周五滚动再定（候选不变：运营端 W8–W10 / R1.1 解冻——09-16 对账归 `archive/PROGRESS-2026-cycle1.md`；远期框架见 §2 W8 起）。

### 0.3 R1.1 — Commercial / Distribution（R1 之后；**排期挂起**）

> 商业化整体挂起：随支付商对接节奏或更后排期，本周不做。批次合同已备（见下表），随时可启动；启动时日期周五滚动定。

| Batch | 服务 | 内容 | 状态 | 依赖 | 施工合同 |
|---|---|---|---|---|---|
| B4b | 资金可用性 | hold GC（资格谓词 = claim 谓词语义镜像） | PLANNED | B4a | `tasks/r1-1-batch-4b-hold-gc.md` |
| B5 | 商业化闭环 | W11 全集：支付/订阅/权益/计费中心/agent_calls 台账（批内前置）/ LinkedIn·TikTok 联调 / 已发布产物 delete 409 | PLANNED | R1（硬前置 = B2） | `tasks/r1-1-batch-5-commercial-distribution.md` |
| C1（并行） | J2 规模化 | skeleton cache identity（唯一索引 = dedupe = lookup + 三戳谓词）；**不阻塞任何 milestone** | PLANNED | 无（顺序上排在 R1 后） | `tasks/r1-1-batch-c1-cache-identity.md` |

外部凭据/平台审批归 R1.1 吸收（mock 验收 + 真联调排队清单），**永不成 R1 的结束条件**。R1.1 之后 = 运营端（W8–W10，§2 既有排期）。

### 0.4 新会话执行规则与启动 Checklist

**事实源优先级**：`Current code > DB constraints/migrations > tests > ADR > 架构文档 > 历史计划`。施工合同里的文件/行号核验于合同标注的 HEAD，**行号会漂移——开工前以 current HEAD 重新定位，合同是导航不是代码事实源**。

**执行规则**：
1. 开工先读 current HEAD 与 git log，不信合同里的行号永远正确；
2. 每个 batch 开工前做 preflight（读合同 + 其引用文档 + 核验代码座位）；
3. 不跨 batch 偷渡未来 architecture；一次只解决一个 correctness/product gap；
4. 每完成一个 batch，从代码重新验证 DoD，不用旧 audit 证明新代码正确；
5. migration / 状态机 / 并发改动必须有 regression scenario；
6. 发现合同与 current code 不一致 → 标记 discrepancy 回报，不自行扩大 scope；
7. 不把 OPEN 产品决策改成 CURRENT，除非该 batch 合同明确要求；
8. 验证纪律：纯函数套件/gate 用户自跑（CLAUDE.md Testing）；e2e 剧本需 dev worker。
9. **认知验收**（ADR-088 Consequences）：触及 agent loop / 意图面 / prompt 面的批，DoD 必答三问——**Agent 看见了什么**（观察合同 ≥ 行动合同）/ **Agent 对「用户要什么」的内部表示是否一致** / **Agent 怎么知道自己做对了**；控制流全绿不视为认知正确的证据。

**启动 Checklist**：
```
[ ] 读 docs/PROGRESS.md §0（当前里程碑 + Active batch）
[ ] 读当前 batch 的施工合同（docs/tasks/ 活跃合同）
[ ] 读合同引用的架构文档（North Star / JOURNEYS / 相关 ADR）
[ ] git log 确认 current HEAD；核验合同中的代码座位
[ ] 确认工作树干净、当前测试基线
[ ] 只做这一个 batch；跑合同 §8 验收
[ ] 完成合同 §9 文档同步（PROGRESS 状态 + commit 号）
[ ] 报告：改动文件 / 测试 / 剩余风险
```

**Non-negotiable constraints**（详表 = `docs/ARCHITECTURE_NORTH_STAR.md`）：LLM 面永不写 DB；拓扑代码裁决；tool schema = action 边界；`apply_wiring_ops` 唯一图写口；`_mutate` 双层 dedupe 永不破坏；clip-spec 唯一渲染契约；打字机律；perception 只读；craft_scan 零 LLM；终态写必须携带执行身份（B2 落地后）；project {PENDING,RUNNING} 至多一 owner（B3 补全到全通道）。

## 1. 产品现状（截至 2026-07-31）

### 1.0 总结

**当前开发目标定位**：面向欧洲知识专家市场（拥有内容却无暇经营自媒体的人——讲者、研究者、讲师，本人或助理操作）的 AI 内容平台——用户上传现有素材（演讲视频 / 会议录音 / 照片·幻灯片 / 文字稿）并点名要的内容，agent 按意图产出：竖屏 clips、LinkedIn 长文、金句卡、轮播、多语言版本皆可单点或组合。产物面宽是能力面，每次交付以用户点名的内容为准，不默认打包（多产物是能力不是承诺；输入不止"演讲"；自称双轨 = 对内 agent / 对外 assistant，NAMING N-25）。

**现状总结**：06-22 启动，六周开发、292 次提交、32 个活跃开发日；9 大模块 6 个已交付，最高优先级需求（P0）清零，已越过"核心功能验证期"，进入冲刺期，至今交付的主干是 **AI 剪辑线**—— 根据真实素材衍生内容（剪辑、改写、翻译配音都基于真料）。**AI 生成线**（没有录像的演讲：文字稿 + 照片 → "你的声音在讲"的视频）于 07-22 立项（双链并列架构）：配音接线已在开发（等待第一张配方卡），"声纹"与"分镜"，"主产物由 AI 虚拟合成"（用用户自己的声纹、照片、文风生成），为下一步工作。

```
上传素材                  生成                       精修                    发布
视频/音频/照片 ──► clips·长文·金句卡·轮播 ──► 对话改·剪辑改·可撤销·内容质量 ──► LinkedIn·TikTok
      ✅            多语言版本·多语言配音 ✅          当前阶段                代码就绪，开发者权限待申请
```

### 1.1 已完成的功能点（按模块，含交付时间）

**1. 内容生成引擎（质量需后续持续优化）** — 上传现有素材，按用户指令产出所点内容（06-22 当周打通主链路）。
竖屏 clips、LinkedIn 长文、金句卡、多语言版本，点名什么生成什么；轮播 / 照片·幻灯片出片 / AI 读图 / 声音克隆多语言配音（06-29 当周补齐）；AI 导演先理解素材（理解结果可复用、不重复花钱）再按论点分派任务（07-27 升级）；每条 clip 带推荐分和理由（07-23）；语音转写精确到每个词；每步成本逐笔记账（07-22）；AI 作曲背景音乐库（07-06）；输出质量第一批：文案锚定原演讲不编造、音量统一、保真检查（07-29）；重活全部后台执行、进度实时可见。

**2. 可撤销编辑地基**（07-26）— 所有修改都安全。
人和 AI 的每一次修改（改标题、剪辑、换音乐、翻译）都记录为可检查、可撤销的操作；网页剪辑器和 AI 对话共用同一套动作——一处改，处处生效。

**3. Chat剪辑（质量需后续持续优化）** — 用自然语言驱动一切（07-26 起持续迭代，07-31 初步验收）。
"剪 3 条 clips 加一篇 LinkedIn 长文"一句话开工；需求模糊时 AI 主动提问对齐（07-30），确认后才执行，不闷头乱做；全屏生成对话：计划确认 → 步骤逐项打勾 → 结果页（07-27）；断线续看（07-28）；完成后说"把第 2 条翻译成法语"即可继续改；"撤销""停下""算了"都听得懂。

**4. 手动剪辑器** — 轻量定位（06-27 落地）。
在文字稿里删一句话 = 剪掉那段视频（不破坏原素材，可恢复）；单轨裁剪 + 实时预览（预览与最终导出完全一致）；专业剪辑需求明确导出剪映/Premiere，不在浏览器重造专业软件。

**5. 一键分发（基础）** — 消灭"下载再上传"（07-24 代码完成）。
产物可直接发布到 LinkedIn / TikTok；发布结果（成功/失败/授权过期）进通知中心。代码已全部完成，待平台开发者权限申请通过后联调开放。

**6. 记忆层（（质量需后续持续优化））** — AI 写得像"你"。
人设（Persona）学习用户的写作风格、口吻和声音（声纹克隆 06-29 接入配音），产物是"你的味道"而非"通用 AI 腔"（LinkedIn 对通用 AI 腔约有 94% 检测率并降低触达）；Brand 皮肤把字体/颜色/logo/字幕样式统一套用到所有产物（06-27 起进渲染）。

**7. 合规底座** — 未开始，已排期（第十三周）。
欧盟 AI 法案要求 AI 生成内容带机器可读标识（2026-08-02 已生效，义务自产品上线日起算）。七家竞品全部缺席——既是入场券也是差异化。

**8. 平台与计费（基础）** — 成本透明化。
每次生成实际花了多少已逐笔记账（07-22）；安全登录已上线；消耗透明 + 积分系统已落地（真账本：开户赠额 / hold→capture→release / 失败不扣费 / 三面展示，ADR-055）；全流程测试批（含积分计算验证）已完成（随 Cycle 1 归档）。待做：套餐定价、支付接入与用户计费中心（属 R1.1，§0.3 排期挂起）。

**9. 获客面（基础）** — 公开落地页 + 配方体验卡。
落地页讲清产品怎么工作（07-25 上线，07-31 视觉叙事改版并完成初步验收）；首页 5 张能力演示卡（07-31 上架），点卡即开发射区（预填提示词 + 上传素材），多语言字幕卡（08-14）与图文视频卡已点亮，演讲短片/访谈分镜/虚拟视频挂 Soon。

**10. 平台工程与体验（跨模块）**
全栈容器化（06-27，api / worker / 渲染 / 前端四服务）与生产环境部署调通（07-15，repurposer.yournpc.ai）；火山引擎 TOS 对象存储接入（07-17，媒体资产云端化、流式播放与下载）；邮箱验证码登录（07-16，两步 OTP 界面 07-28）+ 401 全局处理 + 多用户数据隔离；新用户聚光灯引导（07-23 组件，07-27 首页四步）；全局错误提示与生成进度真实化（07-17 ~ 07-19）；断线可恢复（07-28）；中英文双语界面（07-01 起，英文为源语言）。

### 1.2 产品与调研工作（文档层）

六周里相当比例的工作沉淀在文档层。

| 层 | 资产 | 规模 |
|---|---|---|
| 竞品证据 | 7 家 Top 级别视频剪辑agent竞品调研（OpusClip / Descript / Submagic / Crayo / Repurpose / Revid / ChatCut）+ Opus 三产品线深拆 + ElevenCreative 调研 + 渲染技术选型调研 | `research/` 11 份 |
| 采纳矩阵 | 每个竞品能力逐条裁决：别人有什么功能，uiux交互流程什么样，哪些采纳 / 哪些改造 / 哪些不做——需求池每行都能溯源到竞品证据 | 1 份，持续更新 |
| 战略论证 | 产品定位、哲学、优势、风险 | 1 套 |


### 1.3 近十日交付明细

> 已归档：交付明细逐日实记（07-22 ~ 09-15）整体移至 `archive/PROGRESS-2026-cycle1.md`（Cycle 1 周期归档）。

## 2. 后续排期开发计划（2026-08-03 → 2026-11-17，仅工作日）

**排期口径**：工作日顺排，每周五验收。前五周（意图层 / 人设 / 分镜 / 质量线期 0 / 质量线期 1）已收口。后续排期分为五阶段——**闭环验证 + 8 卡齐亮 + 首页优化（W6）→ FLORA 对齐批（ADR-051）+ 对话工作流批（B1~B4，ADR-052）+ 消耗计算大迭代含支付/积分架构（W7）→ 运营端质量飞跃（W8-W10，内容生产中台 / Memory + 账号体系 / 端到端联调三刀）→ 支付实际开发与分发联调（W11）→ 法务与 AI 合规（W12）+ 缓冲续项（W13）+ go/no-go 评估（W14）**。积分系统批（ADR-055 + 母文档 `docs/BILLING.md`——积分完全先行、真账本、支付只留 W11 边界）已完工；图内核重建批（ADR-057 图即产品对象，简报 `archive/tasks-done/graph-as-product.md`，原型 `scratch/node-ux-proposal.html`）落在 W8 运营端之前——**持久可变图 + wiring 层（chat 唯一消费面，能力完备手势缺席）+ 草稿态（先图后运行）+ 节点五型 + 端口法则 + prompt 直改+确认 + 投影层火化 + 语义账本塌缩**；**执行内核零改动承诺**：compile DAG / NodeBase 四算子 / 队列 / hold→capture→release 全部保留——图的所有权与展示层重建，不是执行层重建。会话层工具 loop 批 + decompiler 批（ADR-077/078）与画布三族批并行跑道。**当前 go/no-go = 11-17，⚠️ 超已批回退位 10-30 十二个工作日；回退路径 = W13 缓冲吃 5 天回到 11-10 + 内核批第二站让位 W8 并行 + W8~W10 三刀压缩，周五滚动定夺**。施工依据：闭环优先于卡片数量（ADR-035/041，简报 `archive/tasks-done/results-canvas.md`）；FLORA 对齐依据 ADR-051 + 简报 `archive/tasks-done/flora-parity.md`；对话工作流依据 ADR-052 + 母文档 `docs/DIALOG_WORKFLOW.md`；积分系统依据 ADR-055 + 母文档 `docs/BILLING.md` + 简报 `tasks/credits-system.md`；运营端排期承接 ADR-042 / 母文档 `docs/POSITIONING.md`；积分批承接第二周 P4 估价地基（`workflow_steps.estimate`）。工期按全栈排实：前端与后端双端各占工期，界面留出反复校准时间，调研 spike 与 e2e 测试显性占行。

### 纵览：十二个阶段

| 周 | 内容 | 里程碑（周五） |
|---|---|---|
| 第一周 | 意图层单面化（chat 唯一入口）✅ + Recipe 数据 schema ✅（08-07） | 意图层单面化落地 |
| **第二周（08-09~08-14）** | **人设模块 + 架构规范化 + 配方卡闭环链**（同周收口） | 人设落地 + dub 配方完全通路 + 多语言字幕卡点亮（R6）+ 开发地基规范化 |
| 第三周 | 扩展配方类型：分镜剪辑 ✅（08-21 验收：双验证过闸 + 双子卡点亮 + 上线前自检） | 分镜能力就绪 + 双子卡 authoring 提前落地 |
| **第四周（08-24~08-28）** | **产物质量线 期 0：解剖**（craft 清单可测量项脚本化 + 全 live 配方卡 × 真素材跑批 + 四层归因证据表，ADR-047 尺子先行） ✅ **提前完成（08-22）** | 证据表落地（每配方 × 四层归因 + 先验校准值）→ `research/craft-anatomy-2026-08-22.md` |
| **第五周（08-31~09-04）** | **产物质量线 期 1：理解层 v2**（节拍地图 schema + prosody 确定性工序 + 上传时跑汇合素材理解前移） ✅ **提前完成（08-23）** | 节拍地图全字段产出 + 词级时间戳零覆写 + asset 级复用（验收三件套 + visual anchors 双半，`scripts/verify_beat_map.py` 全绿） |
| **第六周（08-24~08-28）** | **闭环验证 + 8 卡齐亮 + 首页优化**（首要目标）——4 卡 authoring（voice-dub / social-post / quote-cards / carousel）+ voice-dub 声纹打磨 + 完整闭环 e2e 测试（Remix → 对话定计划 → 生成 → 结果 → 下一步 → 再生产，跑遍 8 卡）+ 首页双形态校准（首次/回访）+ 配方→闭环→选题接力点对齐 | 🎯 8 卡完整通路 + 闭环 e2e 绿 + 首页体验就绪 |
| **第七周（08-31~09-11）** | **FLORA 对齐批（2 天，ADR-051）+ 对话工作流批（B1~B4，ADR-052——余量提前收口 09-04）+ 积分系统批（5 天，ADR-055）**——画布优先路由（overlay 退役）/ 折叠打勾 + 占位物化 / 提问 dock 形态切换 / 节点交互升级 → 改名批（intent_router / understand / plan / pending_brief）+ brief 账本 + ask 一等动作 + 任务书密度律 + 提问机器形态律 + 有界 loop 节点 & research 试点 → **积分系统（真账本，积分完全先行、支付只留 W11 边界）**：configs 公共参数表 + wallets/credit_transactions 三表 + 开户 grant + hold→capture→release 真扣费 + 失败不扣费 + 出生地 shortfall 判定 + 三面展示（dock 总价 / chat 单价 / 配方卡估价贴）+ 余额不足入流灰行 | 🎯 画布/chat 体验对齐 + 对话工作流就绪（裸愿望不再收空心书）+ 消耗透明就绪 + 积分真账本就绪（支付留 W11） |
| **全流程测试批（09-07~09-09）** | **全面全流程测试（含积分计算验证）**——主链走查 + 面板批人工验收 + 09-05 遗留手测项 / hold→capture→release 对账（估价贴 vs 实扣 + reconcile 复跑 + 孤儿 hold P1 复验）/ 边界与回归 | 🎯 全链测试就绪（支付批动工前"敢收钱"状态） |
| **第十一周（09-10~09-23）** | **支付实际开发 + 分发联调**——支付接入（沙盒；钱→积分购买比例与套餐语义本周定）+ 订阅生命周期 + webhook + 套餐权益执行 + 用户计费中心（积分台账投影）+ LinkedIn / TikTok OAuth 发布链路（开发者权限到位 ⚠️） | 🎯 商业化闭环 + 分发就绪 |
| **图内核重建批（09-24~10-07）** | **图即产品对象（ADR-057）**——`graph_nodes`/`graph_edges` 持久图 + wiring 层（add_node / connect / edit_prompt / delete_node / run(_subgraph)，chat 唯一消费面）+ **现有管线迁移上图（修订环根治，首站）** + 草稿态（先图后运行、逐节点估价）+ 节点五型卡解剖（caption 右槽恒空 / 卡面 prompt 区 / factsbar 外置）+ 端口法则 + prompt 直改+确认 + 投影层火化（runFlow 五补丁退役）+ 语义账本塌缩 | 🎯 修订 = 图变更（「Target clip not found」类伤口根灭）+ 画布直读零投影 |
| **第八周（10-08~10-14）** | **运营端（上）：内容生产中台**——选题库（topics + lifecycle + agent + 选题卡发射）+ 内容形态库（分镜 / 脚本 / 预设 / 文章）+ 不同平台 skill 添加（**R5 虚拟视频作为 AI 生成 skill 落位**，ADR-026） | 内容生产中台通路 |
| **第九周（10-15~10-20）** | **运营端（中）：Memory + 账号体系**——Memory（persona）模块迭代（风格学习 + 校准回路 + Voice DNA）+ Persona 显化深化 + 账号体系绑定（**positioning root**：`personas`→`positionings` 改名刀 + 三分区 + `channel_accounts.positioning_id` + 公共档案）+ 定位对话化（意图识别智能化升级并入 W7 对话工作流批 B2） | 🎯 身份复利资产就绪（persona 校准回路 + 渠道有所属） |
| **第十周（10-21~10-27）** | **运营端（下）：端到端联调**——home 改版（回访态 = 选题管道 + 最近产物 + 渠道状态）+ 全链联调（定位 → 选题 → 生成 → 精修 → 发布）+ 闭环质量验证（多 persona × 多选题组合） | 🎯 **运营端闭环 + 质量飞跃** |
| **第十二周（10-28~11-03）** | **法务 + AI 合规**——法务页面 + 用户协议 + 隐私协议 + Cookie 同意 + AI 内容标识（C2PA 选型 + 自动判定 + 披露）+ SEO + 邮件送达 + 监控告警 | 法务 + 合规 + 上线配套就绪 |
| **第十三周（11-04~11-10）** | **缓冲周 + 续项收口**——性能压测 + 文档收口 + 回归全套 + Last-mile 修复（W11 入驻审批 / 开发者权限未到位时的回退位） | 上线前提全部到位 |
| **第十四周（11-11~11-17）** | **全周期验收 + go/no-go 评估**——九阶段成果整体走查 + 修复 + 上线演练 + 🎯 go/no-go 评估材料 + 全周期进度回填 | 🎯 上线 go/no-go 评估材料（**11-17**） |

> **闭环优先于卡片数量**：配方卡全部点亮但不闭环时，期中汇报只能说"还没跑通"；先立闭环，此后每张新卡 = 一行"扩展配方类型"，上线即落入既有通路——叙事从"补窟窿"变成"扩展通路"。哲学论证 → STRATEGY §5；行为规格 → CHAT_ARCH §3.3；形态裁决 → ADR-035/041，简报 `archive/tasks-done/results-canvas.md`；配方数据 schema → RECIPES §7.1。闭环链全部图面由 **FlowView 只读图基座**渲染（ADR-036）——overlay 扇出主视觉 / 结果画布 / 血缘板（复核门），chat 唯一修改通道不变；并直接消费架构迭代红利（ADR-039）：画布节点自动获得友好名，配方卡的流程图与真实执行自动核对、图不骗人。

**外部因素（需按期启动）**：LinkedIn / TikTok 开发者权限（暂缓申请，时间未定——联调排期随 R1.1 重启按实际申请时间重排）；支付商入驻申请（审批周期数周，启动节奏随 R1.1 排期）；律师法务联系（周期 2–4 周——W12 法务落地前提）。术语表、管理后台、帮助中心等最后项按需再考虑。

> **W1~W7 周次实记、三个已完成插入批（全流程测试 / 画布三族 / 会话层工具 loop+decompiler）与 W11 原排期残留**已归档至 `archive/PROGRESS-2026-cycle1.md`；下方仅保留未来周次（W8 起）。

### 第八周（10-08 ~ 10-14）：**运营端（上）——内容生产中台**

> 运营端是质量飞跃的关键（前面只是跑通功能）。本周先把"内容生产中台"搭好——选题、内容形态库、不同平台 skill 一次性立住，给后续 Memory / 账号体系 / 端到端联调提供发射台。

| 日 | 交付 | 验收口径（用户视角） |
|---|---|---|
| 四 10-08 | **选题库**（`topics` 表 + 生命周期状态机：灵感 / 已排期 / 生产中 / 已发布 / 有数据 + API + MODULE_ARCH 表归属登记） | 想到要做的话题有了去处——记下来、有状态、能顺着做下去 |
| 五 10-09 | **选题 agent**（roster 新声明：定位 × 素材档案挖矿，首批选题提议产出——"你那场关于 X 的演讲还没做成过任何东西"形态） | 系统能根据"你的定位 + 你的素材库"端出下一批可做的题 |
| 一 10-12 | **选题卡 UI**（列表 / 状态 / 详情 / 选题发射：点卡 → 任务书预填 → chat 确认即 run，复用 chat 唯一意图面，无第二入口） | 点一张选题卡，计划已经填好，确认就开工 |
| 二 10-13 | **内容形态库**（分镜 / 脚本 / 预设 / 文章 — 形式层 skill 化，统一登记入 SKILL_REGISTRY）+ **不同平台 skill 添加**（**R5 虚拟视频作为 AI 生成 skill 落位**，ADR-026；不同平台 = LinkedIn / TikTok / Newsletter / 网站 等渠道适配模板） | 内容生产有了完整工具集 |
| 三 10-14 | 端到端测试（选题 → run → 产物 → 精修，全链跑通）+【验收】🎯 **内容生产中台通路** | 从"选题"到"产物"通路立住 |

### 第九周（10-15 ~ 10-20）：**运营端（中）——Memory + 账号体系**

> 身份根（persona 校准回路 + 渠道挂根）+ 定位对话化。Memory 是身份复利资产的承载（STRATEGY §2.2 "Identity keeps the customer"），账号体系 = positioning root 落地（POSITIONING.md 母文档）。**意图识别智能化升级并入 W7 对话工作流批 B2**（同一意图面不改两遍，ADR-052——brief 账本就是「chat 多轮上下文加深」的正解形态，定位字段直接成 brief 槽位来源）。

| 日 | 交付 | 验收口径（用户视角） |
|---|---|---|
| 四 10-15 | **Memory（persona）模块迭代**（风格学习 + 校准回路 + Voice DNA 强化——删改痕迹回流 persona 校准，已通过 Operation Model 落地）+ 失败步人格偏移监控 | 产物越用越像你，校准有反馈回路 |
| 五 10-16 | **Persona 显化深化**（风格六件编辑 + 声纹 dub 现状机制不动 + 皮肤块现状不动；用户能看清"AI 学到了我什么 / 在哪里学的 / 哪里不对"） | 维修点从"产品黑盒"变成"我能看懂的特征表" |
| 一 10-19 | **账号体系绑定**（positioning root 落地）`personas`→`positionings` 全栈改名（表 + Alembic / FK 网 / 端点 / 前端路由 / i18n / 存储前缀）+ 内容定位字段入表（territory / differentiation / goals） | 老用户数据与功能零变化；身份从"人设"升为"定位" |
| 二 10-20 | **渠道挂根**（`channel_accounts.positioning_id` + 公共档案字段：昵称 / 简介 / 头像，agent 可基于定位起草）+ 定位页三分区（内容定位 / 人设定位 / 平台定位）+ sidebar「人设」→「定位」+ composer 身份控件随根改名 + **定位对话化**（chat 诊断产出定位草案 + 确认环节——骑 B2 的 ask/brief 机器）+ 回归 harness 全绿 +【验收】🎯 **身份复利资产就绪** | 每个渠道账号知道自己属于哪个定位；身份一页收齐；定位聊出来不靠填表 |

### 第十周（10-21 ~ 10-27）：**运营端（下）——端到端联调 + 质量飞跃**

> 收口三周运营端。home 改版 + 全链联调 + 闭环质量验证。**"用户到来即彷徨"每次访问都要答案**（STRATEGY §5）——这一周是产品从"能跑通"走向"让人感觉到质量"的临界点。

| 日 | 交付 | 验收口径（用户视角） |
|---|---|---|
| 三 10-21 | **home 改版**（回访态 = 选题管道 + 最近产物 + 渠道状态；首次态保留配方卡接住；composer 保留但主 CTA 是选题卡） + 素材上提（assets 归根 = 定位级素材档案） | 老用户打开产品第一眼看到"下一条做什么"；"我所有的素材"一处可见 |
| 四 10-22 | **端到端联调**（首轮对话定定位 → 选题 → 生成 → 精修 → 发布全链；不同 persona + 不同选题组合） | 运营闭环全程走通 |
| 五 10-23 | **闭环质量验证**（多 persona × 多选题组合 + 多平台 × 多语言组合）：发现的问题当天修 | 各类用户群都能稳定走通闭环 |
| 一 10-26 | 修复 + 优化（节奏 / 运镜 / 风格保真等 L2 质量控制补齐打分门槛 / 维度明细 / persona 保真 / 术语表） | 产物"像不像 AI 写的"问题收敛 |
| 二 10-27 | 【验收+缓冲】🎯 **运营端闭环 + 质量飞跃** | 定位可共建、选题驱动回访、渠道有所属、persona 复利沉淀中；产出物带着可辨认的个人印记——产品开始有"高端大气的 agents 团队"的味道 |

### 第十二周（10-28 ~ 11-03）：**法务 + AI 合规 + 上线配套**

> 律师交付卡死这周位置（08-24 启动 → 4 周产出）。AI 内容标识是 EU AI Act Art.50 合规要求，机构采购的入场券。

| 日 | 交付 | 验收口径（用户视角） |
|---|---|---|
| 三 10-28 | **法务页面 + Cookie 同意上线**（律师文书产物落地）+ 用户协议 + 隐私协议 | 服务条款、隐私政策可查；Cookie 提示合规 |
| 四 10-29 | **AI 内容标识**（C2PA 选型 + 自动判定：全 AI 合成必标 / 纯剪辑豁免）+ 标识落地（导出文件嵌入机器可读标识）+ 披露随发布携带 | 产物自带欧盟要求的 AI 标识；机构客户拿去就能合规使用 |
| 五 10-30 | **SEO + 邮件送达**（发信域名认证 SPF/DKIM + 培育邮件）+ 数据生命周期文档 | 搜索引擎能搜到产品；验证码邮件进收件箱 |
| 一 11-02 | **监控告警**（错误 / 可用性 / API 成本异常）+ 遗漏清扫 + 性能优化 | 服务出故障有人第一时间知道 |
| 二 11-03 | 全周期验收 + 修复 +【验收】🎯 **法务 + 合规 + 上线配套就绪** | 上线前提全部到位 |

### 第十三周（11-04 ~ 11-10）：**缓冲周 + 续项收口**

> W11 入驻审批 / 开发者权限未到位时的回退位；正常情况下用于性能压测、文档收口、续项清理、回归收尾。**所有问题应在本周内消化——W14 是 go/no-go 评估，不是修复周。**

| 日 | 交付 | 验收口径（用户视角） |
|---|---|---|
| 三 11-04 | 性能压测（多 persona × 多选题并发；失败不扣费边界测试）+ 修复 | 上线承载量有底 |
| 四 11-05 | 文档收口（用户文档 / 内部运行手册 / 故障应急 runbook）+ 续项清理 | 文档/代码同步上线 |
| 五 11-06 | 回归全套（chat / plan / generation / editor / persona / topics / 8 卡全链路）+ 修复 | 任何一条路径跑都通 |
| 一 11-09 | 性能优化 + 收尾（按压测结果迭代） | 跑得起来 |
| 二 11-10 | 【验收+缓冲】上线前总体检 + Last-mile 修复清单 | 准备 go/no-go |

### 第十四周（11-11 ~ 11-17）：**全周期验收 + go/no-go 评估**

| 日 | 交付 | 验收口径（用户视角） |
|---|---|---|
| 三 11-11 | 全周期走查（九阶段成果整体过一遍）+ 发现问题修复 | 上线前完整体检 |
| 四 11-12 | 修复日（吸收走查发现的问题） | 已知问题归零 |
| 五 11-13 | 上线演练（端到端全路径 × 2-3 真实用户） | 真实用户能跑通 |
| 一 11-16 | 演练问题修复 + 配套准备 | 就绪 |
| 二 11-17 | 🎯 **上线 go/no-go 评估材料** + 全周期进度回填 | 一份"能不能上线"的完整评估，交付总监 |


### 需求池（未排期，常驻节）

> 本周期十二周计划之外的已登记需求。已完成行、已兑现 P0 不在此列（见 §1）；触发条件驱动的需求见下方"可选需求"；明确后置的见"明确不在本周期"。

| 需求 | 优先级 | 依赖 | 来源 / 备注 |
|---|---|---|---|
| 首发推荐分：维度明细 | P1 | 首发推荐分持久化（✅ 07-23） | 矩阵 §C；STRATEGY §2.1（品味可见可证伪）；简报 `tasks/output-quality-verify.md` 覆盖一部分；结果网格重构（第二周闭环链）时汇合评估 |
| persona 校准打分 | P1 | 内部校准源 = 用户选用行为 + operations 编辑痕迹（✅）；外部源 = 发布回流（本周期外） | 矩阵 §C；STRATEGY §2.1/§2.2；账号体系绑定（positioning root 落地，W9 运营端中）后重定座标（校准对象 = 定位的人设分区） |
| 结构化节拍图 + clip-spec motion 枚举 | P2 | 覆盖问责（✅）；限 video 源 crop 动态预设，落地需新 ADR 明确与 stills Ken-Burns 拒绝的边界 | STRATEGY §2.5；与智能分镜线（第三周）汇合评估 |
| 去静默 / 去口头禅 | P2 | 词级时间戳（✅）；随 editor 一键操作方向评估 | 矩阵 §B（下放理由：演讲密度低 + 跳剪伤专业感） |
| LLM provider 抽象 | P1 | ADR-025 已决（薄接口）未实施；触发 = EU 客户要求 Mistral/EU-hosted | 2027 架构（MODULE_ARCH §4.1）。UX 形态：用户-facing 是**策略开关**（如"优先 EU 托管模型"），不是模型 SKU 货架（对照 Lovart 模型选择器，否决）；composer 无模型 pill（管线按模态分派 provider，pill 无法诚实展示终值）。实施第一纪律 = **边界规范化**（dsh defensive-patterns「公共约定两侧都要遵守」：provider 的多种失败形态在边界单态暴露，消费方永不猜异常来源，`research/deepseek-harness.md` §3） |
| 字幕翻译 + 校对视图（side-by-side） | P1 | 多语言输出（✅） | 矩阵 §G |
| 多语言文案质量（Voice DNA 跨语言保真） | P1 | 术语表（下方可选需求） | 矩阵 §G"极高"；STRATEGY 牌 4 |
| 产品度量地基（漏斗埋点：上传→生成→精修→发布→回流） | P1 | 无 | 审计登记；文档坑位 METRICS.md（README 已登记） |
| 一回合多交付（user-facing checkpoint 通道，ADR-085） | P1 | ADR-084 言语语义管线（✅）；感知族读工具（✅ T2b） | 四点收口规则：① 命中率验证义务——主路径单读直出结构性零 checkpoint 非缺陷（判断句住终答），实测系统性过低才重审路由；数据面 = `tool_loop_checkpoint` 日志 + S21 探针 ② iteration-0 豁免 = 防御兜底非产品行为（纯套件锁定）③ checkpoint = live delivery 非 durable——回合失败随事务回滚，不扩事务模型 ④ eligible 资格纪律常驻。验证待用户自跑（纯套件五条路由用例 / prompt gate / S20B+S21） |
| 真实 Gallery（公开项目流入 + remix） | P2 | 配方卡点亮相续（字幕卡 / 图文视频 / 分镜双子卡 ✅ 均已点亮；画廊 v2 八卡批次窗口待指认，ADR-048）；projects/outputs 公开性字段须先 MODULE_ARCH §4 登记 + ADR | STRATEGY §5 Phase 2；配方=数据 schema（RECIPES §7.1）使"用户发布的可 remix 项目"可直接序列化为同款数据包 |
| 虚拟视频卡（画廊 v2 出列） | P2 | R5 作为平台 skill 落位（W8 运营端上）+ 真实成对示例可烘焙 + 两级闸门重过 | 画廊 v2（ADR-048）出列：趣味/实验定位过不了闸门① 场景真实性（知识专家的高频真实场景是把已有素材变成内容，不是生成虚拟分身）；出列 ≠ 否决——R5 作为 AI 生成 skill 在 W8 不同平台 skill 添加批次同批落地，管线就绪且能拿出真实成对示例后按 RECIPES §4.8 重新挣座位 |
| 使用示例跑一遍（demo 素材试跑） | P2 | 配额成本控制形态（试跑限次 / 免费额度内抵扣）；demo 素材已在桶（✅ `demo/uploads/demo_talk.mp4`） | ElevenCreative 配方 modal "使用此示例"证据：访客零上传以烘焙 demo 素材试跑配方，增长向入口；试跑 = 同一 chat 主线（配方播种 + 自动 Start），非独立通道 |
| 模型 EU-hosted 选项（Mistral 等） | P2 | provider 抽象（上行） | 2027 架构 |
| 渲染服务源站限速韧性 | P2 | 无 | Remotion 内部 asset proxy 的服务端 fetch 不走系统代理，本机直连 TOS 被限速（~110 KB/s）时取帧超时全盘皆输；当前缓解 = 渲染进程带 `HTTPS_PROXY` 环境变量；长期项 = 源下载落盘再渲染 或 renderer 显式 proxy dispatcher |
| persona 精修 chat 化（per-field 再提炼 + merge 语义 + 单一对话微调入口） | P1 | 人设页渲染重构（简报 `archive/tasks-done/persona-style-panel.md`，第二周顺做）；一面一 MentionEditor（✅） | 外部评审建议（经闸门过滤）：现状 `generate` 全量重写覆盖用户手改，per-field 再提炼必须带 merge 语义（手改保留，对齐 chat 恒胜原则）；对话微调 = persona 级**一个**入口，禁每模块一个气泡；定位根重构（ADR-042）落地后入口改挂定位的人设分区 |
| persona AI 印象摘要字段 | P2 | persona 提炼链（✅ `POST /personas/{id}/generate`）；摘要进 `PersonaContext` + 表列 | 同上来源：概览卡顶部"一句话画像"。无摘要版概览卡（现有字段拼装）已随渲染重构落地，本条目只补 AI 生成的那一句 |
| insert_broll 技能（layers 家族第一个技能住户） | P1 | 轨道模型 layers 契约（ADR-044）；`slide_pages` 已在跑（✅）；排在 reframe spike 结论之后 | 语录评审：「我讲到增长数据那块，画面切到我的幻灯片」——知识专家最强的 B-roll 场景（自己的幻灯片/截图）；缓议理由只覆盖 stock B-roll。全链拆解归简报 `archive/tasks-done/track-model.md` §7.3（LLM 只做语义定位，机械工序选页+取窗 → layer 条目） |
| SSE 收官散文回合 | P2 | 无（run 收官钩子在） | 语录评审：打勾流 recap 之外追加一个 assistant 收官回合（"做好了 3 条短片，第 2 条最强因为……；下一步建议：……"）——一次调用，是"到来即彷徨"用户的闭环接住点（STRATEGY §5）；不是进度（不违 ADR-041 打勾流唯一进度面），是收尾 |
| landing 叙事骨架重构（六幕 + 商务尾） | P2 | 配方真实产物密度（FlowView 精致度包 ✅ 已备）——存量不到位撑不起证据铺满的骨架，缓做裁定不变 | 六幕结构：`LANDING.md` §4 P2 骨架条（幕表 + 商务尾 + 背书插槽 + 文案纪律）；原始证据 `research/flora.md` §2 |
| reframe per-clip 检测缓存 | P2 | speaker_map 素材级事实（✅）作缓存源 | reframe 线评审遗留：reframe 节点每 clip 启动重探测（~2.5s/clip），同素材多 clip 重复付费，speaker_map 结果可复用 |
| morph 罕见拓扑双渲染 | P2 | 无 | 同上：non-fork→fork→non-fork 的无 producer 链形下，抑制与 rescue 可能双付一次渲染（exotic，perf 项） |
| pre-fail rescue 步骤标签纠偏 | P2 | 无 | 同上：rescue 重挂的 render 步骤行误标 "skipped: upstream failed"（纯展示错，产物正确） |
| reframe phase-2 残毫秒竞态 | P2 | 无 | 同上：检测窗内并发编辑经增量重放压制，仍存毫秒级残口 |
| undo 重挂的陈旧 MP4 处置 | P2 | 产品拍板 | 同上：undo 触发重渲染后旧 MP4 仍挂产物行（OpsCard 侧留有死代码）——清还是留，待产品裁决 |
| 编辑器 staleness 模型统一 | P2 | 无 | 同上（既有类，非 reframe 批引入）：编辑器对 run 中途变更的感知模型 |
| 定点 reframe 报价虚高 | P2 | 无 | reframe_clip 的 estimate 对全项目 clip 求和而非 target_output_id 目标集——纯展示，不阻塞 |
| 字幕简繁归一跟 target_language | P2 | 无 | whisper 对台湾腔国语源出繁体字幕（競爭/協同），LLM 标题按 zh 写简体（竞争/协同）——同帧简繁混排在 demo 里可见。字幕层按目标语言做简繁归一（ASR  verbatim vs 展示一致性的取舍先拍板） |
| agent 调用台账（agent_calls 落库） | P1 | 无（Model/Agent 单边界与计量捕获点在） | DeepSeek Harness 评审（`research/deepseek-harness.md`）：assistant/message 纪律——每次 provider 调用（含空内容 / max-tokens / 校验失败的首试）都是落库事实，usage 永留；现状只记钱（cost），修复一轮不留痕，harness 质量信号（修复率 / schema 失败分类 / prompt 版本回归）与失败取证全丢。质量线补三信号 schema（`archive/tasks-done/output-quality-line.md` §2.6）：过程信号（repair 轮次 + diff 幅度）/ 机制信号（质检违规类型分布）/ 地基真值信号（用户 edit-ops 按节点归因——欠交付节点靠它指认）。台账 = ADR-025 计量纪律从「钱」扩到「调用事实」（agent 名 / run+step / attempt / outcome∈ok·repaired·failed·empty·max-tokens / tokens / 错误类 / prompt 模板名）+ **取证级**：调用 envelope 可重建（渲染后 prompt / schema / 装配上下文哈希，大 prompt 走对象存储 spill——model-visible ⟺ logged 的账簿形态；行业座位 = Agno Traces），挂 R1.1 成本校准闭环做前置；动工时补 ADR |
| 闸门编目（invariants 登记表） | P2 | 无 | 同上评审（dsh invariants 子系统）：偷编目不偷框架——闸门家族（出生地 ∀ 校验 / 启动自检 / 运行时数据闸：撤段序单调性、harvest 带因即拒、叙事闸）散落无名录、按事故逐个加；一张登记表（名字 / 位置 / 统一拒绝形态）让全家一眼可查、可 grep、可进文档。补两条深设计：**explained-empty**（无闸模块须写 `No runtime invariant: <原因>` 式显式说明，防「忘了闸」盲区）+ **闸只断言自有数据关系**（事件流 / 可变数据的关系，绝不断言服务或方法存在性） |
| LLM 录制回放层（MiniMaxClient 边界 record/replay） | P2 | agent 调用台账（上行，同边界同批可并） | 同上评审（dsh `llm-replay` 包）：适配器 seam 录制真实 provider 流成 fixture，无密钥确定性回放——代码侧漂移变确定性回归（注册表扰动的零假设测试从此免费）、PR 可审 transcript diff；全真剧本测试 保留做行为探测，分工 = dsh snapshot（无密钥） vs test:e2e（带密钥）格局 |
| 执行中自适应重规划（interrupt + 重 authoring） | P1 | interrupt 节点（✅）+ 任务书 refine 链（✅）；与素材理解前移（✅ 已落地）互补，agent 调用台账（上方 P1 行）供取证 | 必做：run 中途节点产出的事实与任务书假设矛盾（ASR 检出素材语言 ≠ 任务书语言、素材内容与预期不符等）→ 自动 interrupt + 模型重 authoring 一版任务书，diff 确认后续跑——人在环重规划，**非 tool-loop**（常备否决不变）；预计 2–3 天，排期窗口待指认（建议台账前置之后；插入周内需指明替换项）。**路由判据**（ADR-047 重规划边）：质检失败的机械路由——修复所需信息不在理解层 schema / 超出单节点参数域 → 交还意图层重规划；retry 不中自动升级；素材级不足走诚实降级（不假造钩子）。模型驱动编排永禁，边界明文化（模型编排 = 禁；节点内有界环 = 合法） |
| EU AI Act 内容标记（"AI Generated" 默认开 + 设置可关） | P2 | 合规立场实装（合规包本周期外）；标记形态 = 渲染/导出期，不依赖发布通道 | ADR-046 登记；MiniMax 水印弹窗先例（`research/minimax-design.md` §2：默认开 + 告知去哪改 + 唯一主按钮）；EU AI Act 偏好项 `research/flora.md` |
| TRANSCRIPT 资产生产侧语言印记 | P2 | 无（消费侧已在：`_project_source_language` 读 `meta.language`，08-28 P2 扩展至 TRANSCRIPT） | quote-cards v3 P3 烘焙登记：视频/音频由 ASR 盖 `meta.language`，文本族 processors（transcript / docx / pdf 上传链）不盖章——alt 推导对纯文稿项目缺源语言锚（烘焙脚本手工盖章绕过）；盖章点 = 各 text processor 完工处（语言探测或上传者声明） |
| verify judge QuoteReadability schema 回归 | P2 | agent 调用台账（上方 P1 行——outcome 分类天然承载此类回归的取证） | 烘焙命中：MiniMax 对 QuoteReadability 出 per-quote 裸数组（`[{quote, context_read, standalone, issue}, …]`），pydantic 期 object，schema repair 一轮仍败，`verify_judge_failed` 后 verify 降级完成（产物不受影响，judge 信号缺失）；修法 = prompt/schema 对齐或裸数组→wrapper 边界归一 |
| S41 media_text_fallback × repair 组合漂移 | P2 | agent 调用台账（同上——funnel 行为的取证面） | 全套件跑红揪出（main 上既有，非 quote-cards 轮引入）：S41 7a 期"media 降级在 attempt 内部完成、不吃 repair 轮（pre-echo）"，实际 schema 拒绝直接烧掉 repair 轮且媒体未降级（payload 仍 parts 表 + 带回显）；生产两处 `media_text_fallback=True`（clips agents / registry:91）在册；修法 = base.py 降级时机回 attempt 内，或断言改述现行为 |
| 步骤级 LLM 命名（per-task `name`） | P2 | 展示文案二源律（✅ ADR-058）——run 级 name 已通，本行补 step 级 | **「下批就做」（排期窗口待指认）**：全量形态 = 「tasks 的步骤也是 LLM 命名就没有文字核对问题」；`taskLabel` 链推导已收窄为回退 + 手改撤名已落，步骤名全量 LLM 化 = name 进 TaskItem + builder 钢印位 + RunTaskList/打勾流读法 |
| stub 塌缩（"No source material" 行） | P2 | 无 | 挂账：无素材 writer-only run 的 stub 行应塌缩不渲染 |
| mobile OutputChatCard 核对 | P2 | 无 | 挂账：focus 机制退役 + runTitle 章名后，移动端产物卡读法一致性核对 |
| MG 动画工具（generate_motion_graphics 类） | P2 | 画布三族批两站机制（批 A3）+ clip-spec `motion_graphic`/`text_callout` 元素枚举（已在 schemas.py）+ Remotion 渲染面 | ChatCut 参照：「AI MG动画，生成后还能继续改」= 两站模式复用——MG 脚本（type=table × prototype=manual，行 = 场景：时间窗+文案+动效说明）→ MG 成片（video×generator）；「继续改」= 文档站文字层直改→重渲染（零再生成的理解重买）或 chat 修订→版本分页；画布架构零新增 |
| 对话剪辑工具族（cut / stitch / reorder —— ChatCut「AI 视频编辑器」方向） | P2 | 三族批落地 + L3 铁律边界复核（铁律管的是我们自建编辑 UI 的多轨时间线，不管 agent 能力；专业需求仍导出剪映/Premiere） | ChatCut 参照：「用对话来剪辑你的视频」= video×editor 节点 + chat 修订循环（修订 = 原地图变更现成）；缺的只是工具注册表里的剪辑 tool，不是画布架构 |
| 能力画廊 generate/edit 分组徽标 | P2 | 三族批 prototype 属性落地（批 A3 C2b） | 词表评审（ElevenLabs/ChatCut 参照）：generator/editor 轴的产品显性化座位 = 配方画廊分组 / 卡片徽标（读面派生：有媒体入边 = editor），永不是节点 type；Ele 的媒介 tab 同法可从注册表派生 |
| quotes/carousel 两站拆分 | P2 | 三族批两站机制（✅，translate/dub 先例） | 三族批简报 §7.3 遗留（简报 `archive/tasks-done/graph-canvas-three-families.md`）：quotes/carousel 现单站 image×generator——拆「文案稿 doc 站（table×manual）+ 图装配站」同款两站，改文案零重买图渲染（billing 对账可见 renderer capture 为 0） |
| 样式覆写 UI | P2 | 三族批 editor 卡程序区（✅）；`style_overrides` JSONB 地基未落 | 三族批简报 §7.3 遗留：装配节点 `style_overrides` 数据层 + 用户面（杠杆行形态归批 B4 一并设计；皮肤六件之外的 run 级覆写） |
| 分镜表表格档节点（rev 迭代） | P2 | 三族批表格档先例（✅ 译文/配音稿两站）；编辑映射 op 设计 | 三族批简报 §7.3 遗留：plan 的分镜产物（槽位 + 覆盖理由）持久化为表格档节点（transcript 与 clips 卡之间），删行 = 弃选 / 改时间窗 = 重切 / 改论点 = 重选——全部确定性 op；用户原话挂头 |
| 能力缺口喂给（decompiler gaps → 需求池候选） | P2 | decompiler 骨架（✅，ADR-078 判词②）；缺口观察积累后再按价值排期 | T5 落地登记：拆解时契约无座位的字段 = 诚实「做不到」清单（CraftGap）；`unsupported` = L3 线永不承诺，`not_yet` = 契约座在、写手未到——**not_yet 族即本池候选源**（既有对应行：text_layers → MG 动画工具行；broll_overlay → insert_broll 行）；旅程二 2b 的带理由纠偏消费它，运营侧按观测频率升格排期 |
| Turn budget = iteration cap + wall-clock deadline | P1 | 交互完整性批 A+B+C（✅）——turn_state 状态机与准入门在 | 事故归因挂账：`max_iterations=6` 只封次数不封时长——多轮 quiet read 把回合拉到 60s+，是 abort/超时暴露面与 trigger 竞速窗的放大器；到期的诚实降级形态（cannot-do 行 / "仍在处理"提问）随施工定，不借本条开启 AgentBudget 大架构讨论（North Star 触发制不变） |
| turn 级事件可观测性落库 | P2 | agent 调用台账（上方 P1 行——同取证面，天然合批） | 事故死因不可考的根：stdout 日志不持久 + 回合中途死亡零痕迹；turn_state 已有 in_flight/failed 两章，本条补的是「为什么死」（拒绝轨迹 / 异常类 / 耗时剖面落 DB，非日志文件） |
| 画布可读性②（同族链分组 + 长边路由 + 居中） | P1 | ① 高度失真 **✅ 已落**（ADR-082 判词①——`layout.ts` settled 分支空气压缩：同列按当前渲染高堆叠、`min(serverY, …)` 结构保险、服务端帧零改动）；`GroupFrames` 组件现成（配方说明书先例） | ADR-082：呈现/语义隔离铁律——禁为排线造语义节点；本行剩余 = 同族链分组（项目页补传 groups）/ asset→asm 跨列长边路由 / settled 路径居中；验收同 5 秒三问。**由 Product Flow Alignment Batch C 吸收施工**（合同 `tasks/product-flow-alignment.md` §7；layout 错位 root cause L1-L5 归该批，本行三残留随批吸收或拆分回登） |
| 零探索退化形态（propose_tasks / select_clips LLM 可见性退役弧） | P1 | ADR-089 §8 迁移弧收口（edit_graph 退役证明 = 迭代三 S8 先行；select_clips 裁决已落） | 旅程四拍 0 / ADR-089 §8：干脆请求（范围清晰，ADR-088 §9）在新世界 = Content Plan 的零探索退化形态——单 plan 直产不经探索链；落地后 propose_tasks 与 select_clips 的 LLM 可见性随旧路一并退役。词汇卫生动机（执行世界词表收口），非产品动机 |
| 深度 reviewer / 看片复核 | P2 | 视频理解 provider 能力与成本评估 | 旅程四 B7 挂账（ADR-088 §8）：reviewer 现界 = 确定性 verify + plan 意图比对；「看片复核」（渲染产物内容级自检）缺稳定 ground truth 与成本模型，需求观察后再评 |
| 常驻自主拨盘（standing autonomy dial） | P2 | R1.1 商业形态（订阅 / 额度信封） | 旅程四挂账 B6：Claude Code auto-mode 参照——常驻授权信封（如「N 积分内自动确认」），费用语义在设定信封时一次性披露；ADR-087 D1 退役的 review 档不重开，商业形态明朗后随 R1.1 评 |
| 选项唯一座位（消息流零选项，ADR-100） | P1 | 无（拍板已落：ADR-100 + 施工合同 `tasks/options-dock-only.md`，O1→O3 三批） | live 实锤：answer+suggestions 建议卡与 dock 选项视觉同构、机器两套，用户把正常渲染误报为「dock 变形失效」bug；翻 ADR-099 §2 suggestions 行/§3/§4 answer 面，恢复 ADR-081 全强度；trigger 建议 dock 机器不动；「建议卡发射率」行随批消亡（方法迁移 probe I 新靶）；排期窗口待指认 |
| 素材待命场景重写（回合内有界等待，ADR-101） | P1 | 无（拍板已落：ADR-101 + 施工合同 `tasks/material-wait-in-turn.md`，W1→W3 三批） | live 实锤：素材处理中提问 → 承诺与 beat 事实因果颠倒 + 35s 死窗 + 二手答案（三 writer wall-clock 合流 ≠ 因果序）；回合内有界等待（configs `chat.material_wait_secs` 默认 120s，上界受 trigger 礼貌窗 300s 约束）+ 承诺机器整台退役 + 复读禁止律（内容重复永禁；consumed 双写口谓词，超时地板 = 宣告零内容 + review 必达接力）；正文全打字机拍板确认（G2+drain 终态）；「Turn budget」行的诚实降级形态随批定形；排期窗口待指认 |
| Canvas 密度组织学（journey 分组 / 折叠 / 归档） | P2 | 旅程四实施批（R24 `journey_id` 身份落地 = 前提契约，ADR-088 §10） | 旅程四拍 10 挂账：活跃项目多旅程后画布节点密度（候选合集 / 精选 / 方案 / 产物累积）——分组 / 折叠 / 归档的呈现层方案；禁为组织造语义节点（ADR-082 呈现/语义隔离铁律同律） |
| FRAMING 默认参化（blocking framing ask 拆除，批H 候选） | P2 | 交互架构批 B 验收（caption_mode 默认参化 = 同构先例，ADR-099 §8）；speaker-form block 装配（✅） | 访谈/单讲素材的竖屏镜头选择现为 prompt 法（compose 进链或 ask_user framing choice，intent_router FRAMING 律）——与 caption_mode 同构，可降为方案默认参（推导默认 + 卡面可见事实行 + 手改通道），消掉又一个 blocking ask 场景；批B 落地验证同构性后评估施工 |
| operations 用户级 undo/restore UI | P1 | 精确编辑迭代收口（REST 面全通：undo 回滚 + journal 可溯 + restore 换态 + 归档 409） | 已裁定不新增 `undo_edit` chat 动词、不做完整 version UI；用户级最小回滚 UX 的形态归 P1 简报——画布卡面 factsbar 或产物档案内的 undo/restore 入口 |
| set_caption_visibility（edit_output 第五件） | P1 | 精确编辑迭代收口（前四件野外形态观察期） | ADR-090 §1：与 caption_enabled 计划默认纠缠，先观察前四件野外形态再定参数形状 |
| 失败渲染 → 节点滞留 running → reaper 重跑（重型副作用） | P2 | 图生命周期层（ADR-051/056/057 族，非精确编辑迭代引入） | live 验收取证：编辑触发的重渲染失败后节点滞留 running（revise 门 422 正确拒绝），~15min 后 reaper（reaped_stale_nodes 900s）重跑 select_clips = 整链 wipe 再生——恢复机制的副作用比故障本身重；评「渲染失败 → 节点落 failed 可重试」而非 reaper 全链重跑 |
| drive-4 未复现异常留观 | P2 | 下次 live 验收窗口 | 一次性现象（证据随 cleanup 销毁）：① run 25min TIMEOUT 但双渲染 completed；② 多义问题挂着时带 pin 编辑 /chat 500——定向复现（`scratch/repro_chat_500.py`）未重现（201）；重现即取证 |
| 归档 version 存储成本观察 | P2 | 精确编辑迭代（上行——归档写门落地后开始累积） | ADR-091 §4 挂账：归档 version 文件全保留（回滚的物理基础），GC 只随项目删除；观察存储增量曲线后再评压缩/清理机制，不预设 |
| R1 残留收口（remix e2e S16 + 测试地基复位） | P2 | 真实 Gallery 行（remix 通道，上方 P2） | 配方线收口清单：remix 全链 e2e 剧本座（S16）+ 剧本 fixture 测试地基复位；同清单的 run 路径触发回合与 prelude-free 出生已分别随 Lifecycle Phase 5（trigger_events 白名单缝）与迭代二（prelude-free 出生）落地 |
| 纯 pytest 11 个既有失败复核 | P1 | 纯函数套件（tests/*_pure.py）全绿承诺 | 批次二交付报告（2026-09-29，stash 零假设证为树内既有、与该批无关）：decompile×1 / graph_wiring×8 / import_direction×1 / wire_tiers×1，涉 node_runners.py 等未触文件；回归引入点未定，复核后归位 |
| trigger beat ③ 引号质感例句（prompt 卫生） | P2 | prompt 面（`trigger_system.j2` beat ③） | 批次三观察项：与 W3 整删的 beat ① 同族——引号例句 = 被抄模板，FREE PHRASING 律违反；风险较低（质感示范非否决判句），下轮 prompt 面批次同批评审 |
| 能力菜单欠卖族（dub_clip / remove_filler） | P2 | 能力问答面（`_MENU_PHRASES`） | 批次三观察项：dub_clip 不说声纹克隆（catalog description 有 "persona's cloned voice"，差异化 moat）、remove_filler 只说 filler 不说 repeated takes——欠卖类同 reframe 旧行；措辞升格参照 W5 真值先行法（读 procedure 全量再措辞） |
| 建议卡发射率（probe I 拆双指标 + substrate 先查） | P1 | 无（gate 仪表与 stub execute 在） | 迭代二收口拍板：probe I **不降阈值**（8/12 保留为原始质量目标，首读带 4~6 未达）拆两指标——**路由安全**（present_plan/ask_user 劫持零容忍；本批 24 样本零发生 = 通过）+ **建议发射率**（pre-D 面同带复现 = 既有弱点非回归）；发射率分层——纯能力问建议卡可选（不硬约束），有素材/明确下一步的探索问缺失才计失败（probe I 拆两子场景）；改进路线 substrate 先查（固定模型/参数/场景重复采样，记录原始输出 → 工具调用 → 应用层处理，定位失败在模型未提 / 未调用 / 被丢弃哪层），确认 prompt 约束不清才修 prompt；failure-tag 待补 `answer-args-invalid` + `suggestions-semantic-invalid`（后者先人工标注，不立自动 evaluator）；**ADR-100 拍板后本行观测对象消亡**——answer+suggestions 形态拆除（`tasks/options-dock-only.md`），probe I 随 O2 改靶 browse→ask_user，substrate 先查方法与路由安全零容忍断言随批迁移 |
| 发射层 / provider 方差受控复测（S5 族） | P2 | 与上行同取证面，可合批 | 迭代二收口拍板：S5 五跑 2 绿 3 红（dialect ×2 + 散文铺计划 bare reply ×1）——不归因 D/E 也不以 flake 忽略；轻量立项：固定模型/provider/温度/工具定义/输入/初始状态重复采样，每次保留完整模型输出 + 工具调用序列 + 终态响应，按失败签名记频率（不只记绿红）；区分采样波动 / prompt 约束不足 / 应用层处理不稳 / 评测器形态过敏四因；同输入固定条件仍频繁不同终态 → 上 substrate 层约束，不叠 prompt 文字 |
| 评测系统语义三修（J6 开工暗示 / D3 拒绝项 / S-adv deferral 座） | P2 | reply_quality_probe v6 基线（✅ `baseline-iter2-final` 已存） | 迭代二收口拍板：① J6=1（「先把这块打出来」go-ahead 腔）保留边缘分不降级——补「未确认却暗示已开工」语义断言（推荐 = 建议+理由待确认，执行语义只在确认后），禁固定禁词表；② D3 判读修正——被拒绝备选作上下文说明 = 通过，误述为可选 = 失败（rejected-alternative 是产品结构非缺陷），禁为得分把拒绝项改回可选；③ S-adv 增 `deferred / awaiting-prerequisite` 合法座四条件（指明具体缺口 / 未验证信息不包装成结论 / 说明下一步不虚构已执行 / 前置满足后能续原任务），泛泛「稍后再看」不豁免；评测从 0/1/2 扩为「判断质量 × 是否合理延迟」两维 |
| fill-keys 读面口径（research facet 折叠 × S1 断言） | P2 | ADR-097 §3 第二层门读面行为（✅ DB 实证在册：research 节点 `artifact_role='facet'` 在库未删，读帧并入 deliverable 卡组） | 迭代二收口登记：research 节点 start 后 stamp 为 facet → 读帧节点数 ≠ draft 节点数 → S1「同节点原地填充」断言红（E3 恢复态同率复现，prompt 零交集）；先拍产品语义（facet 折叠对 research 类节点是否正确的画布呈现），再定修 read model 还是修断言口径 |

### 可选需求

| 需求 | 可以考虑开发的情况 |
|---|---|
| 术语表（固定译法 + 配音发音，约 2 天） | 机构客户对多语言译法一致性、配音发音提出明确要求时 |
| 管理后台最小版（用户 / 用量 / 手动补偿，约 3–5 天） | 上线后运营与客服开始需要后台工具时 |
| 帮助中心内容（约 2–3 天） | 用户自助咨询增多，或机构评估需要产品文档时 |
| 邀请 / 分享回流（约 3–4 天） | 需要启动口碑增长时 |
| 链接导入（Zoom / Drive 持续摄入素材） | 机构客户要求从他们的会议和网盘直接拉素材、不愿手动上传时 |
| YouTube 导入 | 目标用户素材大量在 YouTube 上、且反爬成本评估可控时 |
| 团队协作空间（多成员 / 多人设） | 出现团队型客户、多人协作成为成交条件时 |

### 明确不在本周期（取舍有据）

被外部 agent 调用（MCP）、专业剪辑交接格式、定时发布 / 团队审核 / 发布数据回流、newsletter 集成、欧盟数据驻留。均为已登记项，本周期结束后统一重排。

---

## 3. 外部依赖与决策点

**外部依赖：**

- LinkedIn / TikTok 开发者权限：**暂缓申请（时间未定）**。需以公司主体申请、审批周期数周；双平台代码已完成。联调排期届时按实际申请时间重排。
- 支付商入驻审核：08-14 前提交申请，审批周期数周。
- 法务文书：律师外部产出，周期 2–4 周，08-31 前启动联系。

**需要拍板的决策点：**

| 决策 | 需要谁 |
|---|---|
| 支付商选型（欧盟 VAT 由平台代处理 vs 自建税务）与入驻启动 | 总监拍板 + 工程调研 |
| 目标上线日（go/no-go = **11-17**，⚠️ **超已批回退位 10-30 十二个工作日**；回退路径 = W13 缓冲（11-04~11-10）吃 5 天回到 11-10 + 内核批第二站让位 W8 并行 + W8~W10 三刀压缩，周五滚动定夺；W13 缓冲仍消化入驻审批 / 开发者权限等外部依赖） | 总监 |
| 律师人选与预算 | 总监 |
| 定价套餐的业务输入（档位 / 免费额度 / 计价形态） | 总监 + 业务侧 |

---
