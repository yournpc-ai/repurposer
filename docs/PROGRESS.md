# PROGRESS — 进展、排期与需求池

> Status: 活跃快照（2026-07-31 建，每周五滚动；周期结束归档时 §1/§2 随周期滚动，§2 末"需求池"三表为常驻节，带入下一周期；**2026-09-16 产品-first 重排**——新增 §0 当前里程碑区，R1/R1.1 施工序列以此为唯一事实源，§1/§2 周次叙事转为历史与远期框架）；**Cycle 1（~2026-09-17）历史已归档**至 `archive/PROGRESS-2026-cycle1.md`
> 本文是**排期 / 优先级 / 需求池的唯一事实源**（未排期需求见 §2 末需求池）；其他文档只引用周次或需求池条目，不复述排期。双受众：内部管理 / 投资人可摘录。

## 0. 当前里程碑与施工序列

> 本节是**新会话的唯一入口**：本节 → 当前 batch 的施工合同 → 合同引用的架构文档 → current HEAD。§1 起为产品现状快照与远期排期框架；与本节冲突时**以本节为准**。

### 0.1 里程碑状态

- **R1 — Core Product Beta：✅ 已封板（2026-09-17）**——implementation complete, acceptance closed：四 invariant（I-EXEC-01~04）+ S17 族 + B2 §10.2–10.5 实弹竞态演练全绿。仍 OPEN（有界，不阻塞封板）：baseline LLM 方差族 S1 / S6f / S10（登记在案，非 release regression；follow-up probe 保持 OPEN）。R1 定义 / 批次完成记录 / DoD 全账归 `archive/PROGRESS-2026-cycle1.md`。
- **R1.1 — Commercial / Distribution：排期挂起（2026-09-16 拍板）**——随支付商对接节奏或更后再议；批次合同已备（§0.3），启动时日期周五滚动定。
- **Product Flow Alignment：施工中（2026-09-18 拍板）**——Upload Staging / 统一相位 / Product Graph 语义与 Layout / 画布出生编排四批 + E2E；架构地基 ADR-086（拓扑空间权威三律 + Product Canvas ≠ Execution Graph）；施工合同 `tasks/product-flow-alignment.md`（§0.2）。
- **Agent Interaction & Product Lifecycle Architecture：Phase 0 文档冻结完成（2026-09-19 拍板）**——九轮只读取证 + Architecture Fitness Audit（等级 B——骨架正确、边界重划）的允许重划面落档为 **ADR-087**（五条原则 + Lifecycle / Activity / Confirmation 三合同 + 依赖方向 + Reversal Ledger）；施工 = Phase 1~6 六份简报（§0.2），阶段门禁：每 Phase 全闭环才进下一 Phase。与 Product Flow Alignment（验收中）并行，**C-0/C-1/C-2 保护合同不动**（一切 lifecycle/activity 改造只在 read-side，不进 graph write gate）。
- **Agent Working Loop & Exploration Artifacts：旅程四收敛（2026-09-22 拍板，docs-only）**——Agent Tools 审计（`scratch/agent-tools-audit-2026-09-22.md`：A-1 程序盲改 / P0-① 批准出处缺席 / P0-② instruction 双哲学 / P0-③ 工具词表内部化实锤）→ 旅程四 11 拍模拟（JOURNEYS.md，发现型目标的 Agent 工作循环）收敛：北极星（Agent 主循环 = 生产/修订用户可理解的项目产物，Run = 受授权执行阶段）+ R1~R26 裁决台账落档为 **ADR-088（Exploration Artifacts & Project Working Loop）/ ADR-089（Capability Compilation & Execution Boundary）** + NAMING 探索产物词族（N-55）。施工 = **修复批先行**（A-1 `get_node` + specific_instruction 对账 + read 洞 + SSE 实流 CoT 审计，2026-09-22 已交接新会话）→ **ADR 实施批**（探索族 schema → 探索写门 + 终态工具族 → 编译器 + 决策包/快照 → 修订动词 → propose_tasks/edit_graph 并行→退役弧），排期周五滚动定；**2026-09-22 用户拍板：实施批做三次迭代**——迭代一 = 探索产物族数据面 + 画布呈现（合同 `archive/tasks-done/agent-working-loop-iter-1.md`，当日开工）；迭代二 = 编译器 + 决策包/Confirmed Scope Snapshot（销 P0-①）+ R6 发现型路由 + 主链 e2e 首通；迭代三 = 修订回路 + reviewer + 记忆读取律 + 迁移弧 + 终态对标验收；**验收 = 终态体感对标**（2026-09-22 用户拍板，唯一验收口径）：**OriginCut 左栏体验全等映射**——多段第一人称工作叙事（工艺理由自然段）+ 散文段间穿插证据行（可展开 + 耗时）+ 收官摘要 + 确认只在付费边界（OriginCut 输入框同法："Agent 会与你确认后再实施"）；**右侧时间线永禁照抄**（L3 铁律不变，我们的右侧 = 画布产物图）；可执行检查表 = 六拍体感剧本（直接开干 / 过程可见 / 中途插话免费秒改 / 只在渲染前停一次 / 收官自检汇报 / 一句话修订零仪式），全部跑顺才算成——批次完成度不是验收。实施序 = 工程内部事务（切片优先降风险，不占治理面）；**既有合同零推翻**（确认教义 / scope classifier D4 / draft 图 / dock 唯一座 / trigger turn / 打字机律 / 拓扑铁律全部原样承重——拍 6/9 压力测试在 JOURNEYS 旅程四）。

### 0.2 Active batch

| Batch | 内容 | 状态 | 施工合同 |
|---|---|---|---|
| ~~Docs Slimming B1+B2~~ | 文档历史物理隔离（B1 `e7bb212`）+ 本入口恢复（B2 `fde345e`）——依据审计 `scratch/docs-slimming-audit-2026-09-17.md`；B3+（ADR 瘦身 / 架构文档去重等）重新审计后再评估 | ✅ 完成（2026-09-17，完成即停线） | `tasks/docs-slimming-b1-b2.md` |
| **Product Flow Alignment** | Upload Staging Session → 统一相位/readiness gate → Product Graph 语义模型 + Layout（拓扑空间权威三律）→ 画布出生编排 → E2E——三路 Recon root cause L1-L5 + 用户四决策拍板（2026-09-18）；架构地基 = ADR-086；需求池「画布可读性②」随 Batch C 吸收。**Batch A（upload staging）+ Batch B（相位清除协议 I-PFA-06 定型 + readiness gate I-PFA-07）+ Batch C-0（Product Graph 契约模块 `app/pipeline/product_graph.py` + canonical fixture，只定义不碰布局）代码已落（2026-09-18）**；Batch B 验收 PASS WITH RUNTIME GAPS（P0 runtime checks 用户自跑）；**C-0 收口 = PASS WITH DEBT**（fixture 13/13 绿 + post-compact forensic audit 只读归档；F1/F2 消解规则随 C-1 开工落档，F3 ctx 漂移待裁决）；**C-1（rank 单一事实源接线）代码已落（2026-09-18）**——服务端 `GraphNode.rank` 上线（read-time projection）+ `layout.ts` settled 投影改吃 rank（depthOf 退出图画布路径），vitest 8 例含 L1 旗舰回归 + 错帧双杀镜像 fixture（↔ API 侧互引）；**C-2（RunOp 执行序解耦）代码已落（2026-09-18）**——排序键 = (rank, id) 拓扑序永不读 layout.x，modifier 执行序经 ungated rank 保全，4 个回归新例 75/75 绿。**验收口径 = Greenfield**（2026-09-18 拍板：旧数据兼容验收删除，dev 库 9 个旧项目已清；只验全新项目 → 上传 → Generate → Canvas → Revision 链路）——验收中，通过即 C-0/C-1/C-2 收口，C-3/D 是否动工由产品需求倒推裁决 | 施工中（2026-09-18 周五滚动拍板） | `tasks/product-flow-alignment.md` |

| **Agent Interaction & Product Lifecycle Architecture** | **Phase 0 ✅（2026-09-19，docs-only）**：ADR-087 落档（五条原则 / Lifecycle 五态 + Charge Semantics Ready / Activity 十规则 / Confirmation Doctrine / 依赖方向 / Reversal Ledger R1~R8）+ README 事实源表补行 + NAMING 词族注册与死行清理（过程脊 / 渲染单元 / 结果画布 runFlow 定义 / 焦点注入）+ INTENT_COVERAGE 标记 historical（IC:50 翻案）→ **Phase 1 Lifecycle Projection**（服务端命名谓词，projection additive → dual-read → switch → remove；转写节点 loading 出生随批）→ Phase 2 Activity Projection（追加式活动流，hook 接缝 3 座，无持久化首版）→ Phase 3 Presentation Migration（_read_face / activity_key / THINKING_PHASE_* 归位 + 客户端零 lifecycle 推导）→ Phase 4 Confirmation Doctrine Unification（先盘点 propose 直起 run 清单再改代码；统一 Paid Authorization path）→ Phase 5 Dependency Cleanup（import 图单向，冷导入探针）→ Phase 6 Hygiene（巨文件拆分，永不进关键路径） | Phase 1 **已落地（2026-09-19，Preflight PASS WITH 3 CONDITIONS 后施工）**：`pipeline/lifecycle.py` 纯核+装配器、results/graph 双响应携戳、纯 pytest 19 例绿、转写节点上传即出生、客户端谓词切戳（旧推导归零）——commits 386c62c/8972e74/167638e（worktree-lifecycle-phase0）；未跑验证项在简报 Status 在册（compileall/tsc/剧本 = 用户自跑）→ Phase 2 **Implementation 步①~④ 已落地（2026-09-19，Preflight PASS WITH CONDITIONS——U1/U4/U5 裁定 + T16 拆双不变量 + 连续性≠周期刷新——后施工）**：tool_loop typed `LoopEvent` 通道（U1 冻结边界）+ `chat/activity.py` 纯投影器 + `assistant.activity` SSE 帧 + dock `ActivityStream` 并行渲染（active 在位时 System Status 行让位）+ 纯 pytest 54 例绿——commits 662d88a/fa0df01/a33cae4（worktree-lifecycle-phase2-preflight）；**步⑤（相位面收窄为 System Status 纯基座）HOLD——过剧本 + 产品试用验证门禁后施工**；**Phase 2.5 Verification Contract Migration 已收口（2026-09-19，Audit + Batch A/B/C）**：gate 5a/5b/5c 静态边界三门 + harness Activity-first 迁移 + 合同洞纯测试补齐 + 剧本 fixture 律消灭 worker 竞态 + `tasks/verification-contracts.md` Registry/Known Variance 落档；纯 pytest 305 绿 + gates 全绿 + S1/S5/S7/S10/S11/S20A/S21 线上实证——**Phase 2 VERIFICATION CLOSED**；步⑤ 与旧相位退役仍 HOLD → Phase 3 联动；**Phase 3 Batch A（Presentation Authority + Web Contract Seats）已落地（2026-09-19→20，commits df5de98/e5a95a2/75f0570/ad05a2d，worktree-phase3-batch-a）**：Canvas 确认座退役（判词 1，Confirm/Start 唯 dock pill）+ fallback-to-true 四站点全灭（判词 2，lifecycleStamp 三态谓词 missing≠ready）+ Web 纯缝 contract tests 43 例新增（vitest 52 绿 / 纯 pytest 305 绿 / gates 绿 / S1·S5·S20 回归）；**Phase 3 Batch B（Phase Machine Migration）已落地（2026-09-20，commits 755028f/840e4d4/44b5d4d/046bd9f/b9dc6ee/37e252c，worktree-phase3-batch-b）**：confirm/running 退位给戳（裁定 1——confirmActive 派生谓词 `intentReady && isPlanReady(lifecycle) && !runAttached`，ChatDock `type Phase` 状态机整删）+ drafting/inspecting/repairing 三替身退役（Activity 投影器唯一座位）+ creating_run 经 CDP 死窗取证双场景 PASS 后删除（裁定 2 先证后删）+ composing 幸存 System Status 唯一叙事、永不建相位正向锁（裁定 3）+ 剧本逃生舱/相位断言迁移（SCENARIO_ACTIVITY_LEGACY 归零）——vitest 58 绿 / 纯 pytest 305 绿 / tsc 2 预存错不变 / 验收 grep 门全过；**Phase 3 Batch C（Presentation Contract Cleanup）已落地（2026-09-20，commits c143ad1~1ae164d 七刀 + fbad9e6 落档 + 616435d 尾刀，preflight ef3e6ef 十项裁决）**：C1 +88 几何债删 / C2 `_read_face` DEFER 维持（删除扳机 = DB 守卫查询，prod 挂账）/ C3 DENSITY 渲染断言退役 + 尾刀半句同标准退役 / C4 render_superseded 入注册表 / C5 `chat/system_status.py`（不开 presentation 包，§6 私有 import ×2 灭）/ C6 文档修正 / C7 lifecycle 键恒在 / C8 run 活性 = transport 事实落档 / C9 `chatProtocol.ts` 抽出 / C10 sweep 零回潮——验收（Claude 自跑——用户委托）= 纯 pytest 305/305 / check_gates OK / 剧本 S5·S7·S10·S20 绿（S5·S20A 首跑单发在册方差复跑即绿；S11 红 = §6 在册延期债）/ prompt_gate minimax 三探针 36/36 满分——**Phase 3 CLOSED**；**Phase 4 Confirmation Doctrine Unification CLOSED（2026-09-20 开工 → 2026-09-21 B0~B8 + 修复批全落地）**：Preflight ✅（propose 两直起出口实锤 `propose_turn.py:330`/`:470` + 三锚点更正——R5 前端自动 Start 已于 `43dbda3` 消失 / review=plan path 实发档非死档 / caption fast path=目标形态样板 + 合同外新发现 /generate 灰区）→ Decision Gate 四项终裁 ✅（D1 `autonomy="review"` RETIRE（ADR-087 R9，WAITING_HUMAN 基建保留）/ D2 /generate=SERVER-VERIFIABLE APPROVED RETRY / D3 Start 服务端确认强制（Batch 6）/ D4 continuation/expansion 按结果付费执行范围判定 + Frozen Rule 1~10——Decision Ledger 见 task 简报）→ **B0 Decision Ledger+docs ✅** → **B1 deterministic scope classifier ✅（2026-09-20）**：`pipeline/scope_classifier.py` 纯核+装配器（**零 op 词汇**——用户裁定可扩展性护栏：消费 wiring 门前后图 facts 纯比对，D4 结果 scope 律，新 op/节点族/工具对分类器不可见）+ 链逐字匹配器（历史 run.context 证明 approved retry，D2）+ 27 例纯测试全绿，additive 未接线 → **B2 A2 切换 ✅（2026-09-21）**：edit_graph 按分类器裁决——savepoint 过门 + 门后 facts 比对，continuation 自治直跑（S4-A2 天然 continuation 零改动）/ expansion·unproven 回滚转 dock（caption replay 同款机器，Start 原地填充）；**§8 复议点 fired 同日修正**：`produces_outputs=False` 是 settle 簿记旗非免费标（translate_clip/dub_clip/render/research 全付费），付费标记 = registry-known 即付费；验证 = 纯 pytest 332 绿 + 剧本 S4/S1/S5/S7 绿 + in-process probe 实证 expansion dock → **B3 A1 切换 ✅（2026-09-21）**：propose_tasks 出口切换——同 turn create_run 全路径禁止（caption 闸门顺序不变，validate_task_list 提前到 dock 前喂 loop，出生门其余约束移交 Start 422 同 plan path 姿态），`_dock_plan_as_question` 唯一 dock 座收编 B2 分支；计费耳语 `chargeNote(WithEstimate)` 双形态随行（BILLING §2.1 Held+Actualized 披露闭缝，零机器改动）；剧本 S7-B 翻转 + **S4-A3 expansion dock 座整面落地**（路由无关，同 turn 直跑 = 硬红）+ S4-A2·S7-A·S7-C 保绿；验证 = compileall + 纯 pytest 27 绿 + tsc 零新增错 + 剧本 S4/S7 复跑 → **B4 prompt 合同修正 ✅（2026-09-21）**：propose_tasks / edit_graph 描述与 B3 后真实语义对齐（propose = dock 待确认、run 只在显式确认后出生；continuation 自治 / 新增付费工作转 dock）+ `chat_intent_system.j2:19` "run NEW work" 与 `:23` 失信表述改写 + EditGraphArgs docstring 同律修正（`model_json_schema()` description 上 wire 实证为 prompt 面）——「propose 当轮直跑」残余清零，工具描述 / 系统 prompt / registry catalog 行三处一致，classifier 留代码 prompt 不分类；验证 = compileall + 纯 pytest 332 绿 + **prompt_gate 三探针 36/36 两连 PASS** + tsc 2 预存错基线不变 + check_gates OK + 剧本 S4/S7/S1/S5 全绿（worktree API :8001 + worker，首跑即绿） → **B5 /generate server gate ✅（2026-09-21）**：D2 终裁 SERVER-VERIFIABLE APPROVED RETRY 落地——链分类器两级证明（`exact_retry` 全链逐字 + `family_retry` 单条历史链非空有序子序列，跨链组合/重排/参数改动/空链全部不可证）；路由门 tasks≠None 即查，不可证 → machine-readable 422 `scope.unproven`（先于余额检查，永不 create_run，Rule 9/10）；`GenerateRequest` 四 retry 引用字段（回声 = 引用非证明）+ 前端 handleRetry 全工作字段回声（合法整类重做零破坏，Rule 5）+ ChatDock legacy fallback 收敛非授权通道（`scope.unproven` → 诚实对话确认引导行 en/zh，零新 UI）；D2 六例矩阵 + family tier 12 例纯测试（39/39），S13 种历史链保绿 + 不可证 wire 断言；验证 = compileall + 纯 pytest 344 绿 + prompt_gate 36/36 PASS + tsc 2 预存错不变 + check_gates OK + 剧本 S13/S4/S7/S1/S5 全绿首跑即过；targeted scopes 与 legacy slot-run 不可证在册 → **B6 Start 服务端四合取强制 ✅（2026-09-21）**：D3 终裁落地——`evaluate_start_gate` 纯核（lifecycle.py）+ `answer_question` Start 分支接门（dock pill 与 G-1 散文确认同一座），结构化守卫全机器可读化（`start.scope_mismatch`/`start.already_answered`/`start.no_pending_plan`/`start.empty_plan`/四合取戳未就绪 → 422 `start.blocked` 携戳 blocker ids），「前端按钮 disabled」不再是唯一防线；同批 bug fix（`pending_plan=True` 直传——answer 先写后 dispatch 使 `is_pending_plan` 恒 False，误传全量误阻 0/5 取证后修复）；D3 六例矩阵 8 例纯测试 + S13 活跃 run 阻断 wire 座；验证 = compileall + 纯 pytest 352 绿 + tsc 基线不变（零前端）+ check_gates OK + prompt_gate 三探针全 PASS + 剧本 S13/S1/S4/S7/S5 全绿 → **B7 `autonomy="review"` 退役 ✅（2026-09-21）**：D1 终裁/R9 落地——inventory 先行（grep 实证 `run.context["autonomy"]` 零读者）→ `TaskSpec.autonomy` 整删 + review 分支移除（understand→plan 恒直通），`GenerateRequest.autonomy` 移除（pydantic 默认 ignore 兼容旧客户端），`StartAnswerRequest`/`ChatRequest.autonomy` 保留读容忍（accepted+IGNORED），前端 state/picker/i18n/chat-stream 整块清除，review-tier 纯测试改写为新形态锁；**WAITING_HUMAN/interrupt/expiry sweep/verify escalation 基建零触碰**；验证 = compileall + 纯 pytest 352 绿 + tsc 2 预存错不变 + check_gates OK + prompt_gate 三探针全 PASS（零 prompt 改动）+ 剧本 S6/S17/S13/S1/S4 首跑全绿；dev 库 0 WAITING_HUMAN/0 review-context 行；docs 现在时改写同批（NAMING/CHAT_ARCH/API.md）→ **B8 剧本/验证/docs 收口（施工面 ✅ 2026-09-21）——三项悬案已拍板，修复另批**：WiringProposal docstring 现在时（B4 挂账收口，非模型面——prompt_gate 三探针实证零扰动）+ CHAT_ARCH §3 工具网格两行 + verification-contracts §2 Scope 行 🟡→🟢 + §6 登记（S11 断言迁移 / CHAT_ARCH §8.6 相位残段 Phase 3 债）+ ADR-087 R9 生效登记 + Consequences commit 范围补齐（`b0a3667`→`61181d1`+本批）+ 剧本 S11 fixture 律硬化 / S19 改写 ADR-080 第二谓词端到端座（bail 清 pending）/ S16 exemplar 恢复 FAILED 原设计；验证 = compileall + 纯 pytest 352 绿 + check_gates OK + prompt_gate 三探针 PASS + tsc 基线不变（零前端改动）+ 验收 grep（`_propose_tasks` 零 `create_run`）+ 剧本 S11/S19 绿、S16 红于在册座；**B8 取证新猎三项 doctrine 悬案（verification-contracts §4 注册）——已全部拍板（2026-09-21），修复另起后续批**——① 空散文 dock 永不 ready vs P8「计划散文非空」（拍板 = 选项 B：P8 翻案 → ADR-087 Reversal Ledger R10，确认 scope = 卡载荷，散文降装饰）② 触发回合落点竞态（拍板 = (a) 落点复评命中即整体静默）③ material gatherer 项目级 any()（拍板 = plan-scoped 收窄；S16-P2 Start 红座常驻验收）——**修复批 2026-09-21 落地 ✅**：① R10 生效（`plan_prose` 合取删除，空散文 dock 可确认；T10b 改写 R10 锁 + S19 恢复 Start 形 = 端到端验收座）② 触发落点复评 `is_pending_plan` 命中即整体静默（ADR-080 第二谓词补齐 + S22 常驻回归座）③ gatherer plan-scoped 收窄（pinned exemplar 非源排除，S16 全绿证明）；修复批验证 = compileall + 纯 pytest 352 绿 + check_gates OK + 受影响座全绿（S19/S22/S16/S1/S11/S20；S1·S16 首跑红皆在册方差复跑即绿）+ 全量剧本复跑（见 commit 报告）；其余验收标准均已兑现（新 Paid Work 无确认不起 run / continuation 不误阻 / 两路同一 dock / Rule 7 确定性分类 / D2·D3 矩阵绿 / review 退役基建保留 / prompt_gate 过）→ **Phase 5 Dependency Cleanup CLOSED（2026-09-21，branch `worktree-worktree-phase5-deps`，commits `ca98d86`→`d51c9a7` + docs 批）**：四族机制落地——① `pipeline/trigger_events.py` 白名单事件缝（三 kind 冻结白名单，组合根 app.main/app.worker 双注册，fire-and-forget 未注册 = 静默降级）② `pipeline/conversation_bridge.py` 会话写四命令显式 protocol（同签名 delegate + flush-only 原样 + 未注册 fail-loudly）③ `platform/conversation_context.py` 会话读四助手只读协议座（MODULE_ARCH §4 批准座）④ regenerate 端点迁 `chat/routes.py`（URL/语义不变）——+ `build_context` 迁 `chat/context.py`（agents/contexts.py 裁定落地）+ 32 名私有→公共扶正 → pipeline→chat 8 处清零、跨模块私有 import 87→0、零新增 deferred（71→65）；**探针五牙入库** `test_import_direction_pure.py` green from birth（AST 双门 + 冷导入双子进程 + 接线保险 + 牙⑤改名碰撞扫描）；**修复批 `d51c9a7`（剧本复跑取证）**：`_generation_context` 扶正撞同名局部变量三处（`x = x(...)` 自引用 → S16 P2 plan 节点实红，局部让位 `gen_ctx`，AST 全树实证仅此三处）+ scripts/ 旧名残留两处跟随 + 探针牙⑤同类永禁常驻；验证 = compileall OK + 纯 pytest 358 绿 + check_gates OK + 零 prompt 改动声明（prompts/ 零 diff）+ 剧本 S1/S5/S6/S7/S10/S11/S16/S17/S20(A) 全绿（S16/S20 复跑取证猎得上述两真 bug 并修复；S20A 首跑红 = 披露措辞未匹配，verification-contracts §4 KNOWN VERIFICATION FRAGILITY 正则语序洞在册座，复跑即绿） | `tasks/lifecycle-phase-1-lifecycle-projection.md` / `tasks/lifecycle-phase-2-activity-projection.md` / `tasks/lifecycle-phase-3-presentation-migration.md` / `tasks/lifecycle-phase-4-confirmation-doctrine.md` / `tasks/lifecycle-phase-5-dependency-cleanup.md` / `tasks/lifecycle-phase-6-hygiene.md` |
| **Agent Tools 修复批** | 审计 `scratch/agent-tools-audit-2026-09-22.md` 的两条代码级实锤 + 同族 read 洞（北极星「用户可见 Agent Loop + Canvas Artifact Model」的地基修复，只修不建）：**Fix 1（A-1 程序盲改）**——perception 族加 `get_node` 全文程序读（Graph 段 140 字截断 vs edit_graph「从当前程序合成」规则结构性矛盾；4000 字预算帽超帽诚实标注）+ chat_intent_system.j2 补「修订前先 get_node 读全文」；**Fix 2（P0-② specific_instruction 双哲学对账）**——`ProposeTasksArgs` 加 distilled-EXTRA 字段（对齐 plan 路 schemas.py:1402 / intent_router_system.j2:64 合同），`propose_turn` 改读 params 字段、缺席兜底 `text or None` 保旧行为，合同措辞抽共享 partial `_specific_instruction.j2`（router 渲染 25703 字字节级不变实证），消费口（caption 回放 / Start）不动；**Stretch（§7 d/e）**——`get_pending_plan`（chat 路 docked 计划读）+ `list_runs`（run 历史读）同注册纪律落地。i18n en/zh 双写六键；纯测试 +16 例 | ✅ 完成（2026-09-22，commits `96b43fc` / `2e04328` + docs 批，branch `worktree-agent-tools-fix-0922`，**已落 main merge `c8322fd`**）——验证：compileall OK + 纯 pytest 370/370（合并树独立复跑同绿）+ check_gates OK + prompt_gate minimax 三探针三轮 PASS；doctrine / classifier / loop / 图写口 / service·plan_turn·context 零 diff 实证；e2e 剧本未跑（需 dev worker，用户复跑） | 审计 `scratch/agent-tools-audit-2026-09-22.md`（§3.1 / §2 / §7） |
| **Agent Working Loop 迭代一：探索产物族数据面 + 画布呈现** | ADR-088 §1~§5 地基（三次迭代之第一次，终态对标在迭代三）：journeys 表 + graph_nodes.journey_id（R24 归属）→ 探索三族 spec 形状（CandidateSet 合集 / Select 证据引用 / ContentPlan 产品语义，R1/R3/R7/R8/R9）→ 探索写门（R14 双门：savepoint + 证据校验 + 幂等；探索节点零边；执行写门拒收 exploration 族）→ I-EXPLORE-01 纯测试锁 → 证据 reads（search_transcript / get_segment 注册 perception，prompt_gate）→ 探索终态工具族（EXPLORATION_TOOLS，harness 级不接生产）→ 画布三族卡面（合集折叠 / 精选理由行 / 方案 draft 虚线，R18 不镜像 running）→ S-explore 剧本。**开工裁决（ADR-089 §8 PENDING）**：select_clips 保留为执行工具（零探索退化形态唯一机制），编译器永不从 Content Plan 编译出 select_clips，迭代三迁移弧收口再评退役 | ✅ 施工落地并实测全绿（2026-09-22 施工，五刀：234bdfe 数据面 / 869bb84 证据 reads / 25f4c7d 终态工具族 / 90e936f 画布三卡面 / 110ed4d S23 剧本）——纯 pytest 432、web tsc+vitest 61、check_gates、prompt_gate 36/36、S23 确定性尾对活 API 22/22 全绿；**S23 LLM 三拍挂账已销（2026-09-23）**：配额恢复后 `--only S23` 全量 PASS（三拍全落点 + 确定性尾全过；实测猎得 harness 提示两牙修复 `38a042d`——member 索引 0 基 + 每回复必以 tool call 收束） | `archive/tasks-done/agent-working-loop-iter-1.md` |
| **Agent Working Loop 迭代二：能力编译层 + 决策包/快照 + R6 路由** | ADR-089 实施（三次迭代之第二次，终态对标在迭代三）：编译器（Content Plan → Execution Scope）+ 决策包 + Confirmed Scope Snapshot（销 P0-①）+ R6 发现型路由 + work session 活动键 + revise_plan → 主链 e2e 首通。**逐项拍板制**。**① clip 编译目标 = cut_segments 已拍板并落地（2026-09-23，branch `feat/cut-segments`，commits `b000c05` NAMING / `8e86c9b` PlanOutput 三缺口 / `550a933` 能力+编译路径集成）**——产品先行再裁决推翻首版参数面：params = segments(1..5)+asset_id?+aspect?，caption_mode/language **不进出生参数**（transform 语义各有能力续链）；runner = materialize_source 零 LLM 模板一般化；新注册表轴 `llm_visible`（N-56 compiler-only 公民首座）+ N-32 一类型一生产者收窄到提案空间 + node_for_output 硬化；PlanOutput 产品语义三缺口补齐（+aspect 词表 / +dub / caption_mode 收窄三值，安全窗口 = R6 接线前）+ 方案卡面展示；编译路径窄集成（producer 判定 output_type 声明化 / label 座位 node_cls 直读 / spec 携带 / prelude-free 出生）全部恒等守护既有链。验证 = compileall + 纯 pytest 452 绿（新例 17）+ 启动自检过 + web 零改动；prompt 面字节不变（llm_visible 收窄经一致性测试护航，prompt_gate 无新针）。**②~⑦ + §4.1 + §4.9 全量落地（2026-09-23，commits `c2c65f3` ② writer source_span / `e228ff1` §4.1 scope_compile 编译器 / `d8fefa0` ③ 决策包 dock / `ac5d9fb` ④ Confirmed Scope Snapshot 销 P0-① / `2da1705` ⑤ R6 发现型路由生产接线 / `6a20c8c` ⑥ chat.explore.* 活动键族 / `735631b` ⑦ revise_plan / `8826f71` §4.9 S-explore-2 剧本；词表先行 `9fb9d1e` N-57）**——R14 双门预检编译（不可编译包零写入拒回 loop）、决策包三面（plans 阅读层双座 stamp + 编译链证据可展开 + quote）、快照五字段（confirmation_id/confirmed_at/confirmed_via/plans/compiled_scope+quote）、生产投影终态律（candidates/selects 非终态一回合连续工作、propose_plans/revise_plan 终态 R15 停顿）、手改撤名让座律延及 plans 阅读层。前端：dock 计划卡阅读层（plans 在上 + tasks 证据折叠展开）+ ActivityStream count 透传 + i18n en/zh 双写（generationOverlay.planOutputs.* / chainEvidence / chat.explore.* 五键）。验证 = compileall + 纯 pytest 504 绿（本批新例累计 52）+ check_gates OK + web tsc/vitest 55 绿；**LLM 驱动面已实测全绿（2026-09-23）= prompt_gate 全量四探针 48/48 PASS（A/B/C/D 各 12/12）+ S-explore-2 live e2e 全链 PASS（7 迭代净发现环 → 决策包 dock → confirmed_scope 五字段全等断言 → run completed，clip+post 落地）**——实测猎得三修真修同批（`5c9ac44` asset_id 观察头接力 / 供方 `{"item":...}` 数组方言线级拆包 / loop 预算 8→12）+ S23 提示硬化（`38a042d`，iter-1 挂账同销） | ✅ 完成（2026-09-23，落地 + 实测全绿） | `tasks/agent-working-loop-iter-2.md` |

**下一批**：本轮收口后周五滚动再定（候选不变：运营端 W8–W10 / R1.1 解冻——09-16 对账归 `archive/PROGRESS-2026-cycle1.md`；远期框架见 §2 W8 起）。

### 0.3 R1.1 — Commercial / Distribution（R1 之后；**排期挂起 2026-09-16**）

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
9. **认知验收**（2026-09-22 拍板，ADR-088 Consequences）：触及 agent loop / 意图面 / prompt 面的批，DoD 必答三问——**Agent 看见了什么**（观察合同 ≥ 行动合同，A-1 教训）/ **Agent 对「用户要什么」的内部表示是否一致**（P0-② 教训）/ **Agent 怎么知道自己做对了**；控制流全绿不再视为认知正确的证据（30/30 全绿与 A-1 并存的教训）。

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

**当前开发目标定位**：面向欧洲知识专家市场（拥有内容却无暇经营自媒体的人——讲者、研究者、讲师，本人或助理操作）的 AI 内容平台——用户上传现有素材（演讲视频 / 会议录音 / 照片·幻灯片 / 文字稿）并点名要的内容，agent 按意图产出：竖屏 clips、LinkedIn 长文、金句卡、轮播、多语言版本皆可单点或组合。产物面宽是能力面，每次交付以用户点名的内容为准，不默认打包（2026-07-31 纠偏：多产物是顺带能力，不是承诺；2026-08-01 补充：输入不止"演讲"，自称双轨=对内 agent / 对外 assistant，NAMING N-25）。

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
每次生成实际花了多少已逐笔记账（07-22）；安全登录已上线；消耗透明 + 积分系统已落地（真账本：开户赠额 / hold→capture→release / 失败不扣费 / 三面展示，ADR-055——09-03~09-05 提前完工，对账尺首跑抓获孤儿 hold 真缺口当日修复）。待做：全流程测试批（含积分计算验证，09-07~09-09，拍板（五））；套餐定价、支付接入与用户计费中心排第十一周（09-10 起）。

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

> 已归档：交付明细逐日实记（07-22 ~ 09-15）整体移至 `archive/PROGRESS-2026-cycle1.md`（2026-09-17，Cycle 1 周期归档）。

## 2. 后续排期开发计划（2026-08-03 → 2026-11-17，仅工作日）

**排期口径**：工作日顺排，每周五验收。前五周（意图层 / 人设 / 分镜 / 质量线期 0 / 质量线期 1）已收口。后续排期分为五阶段——**闭环验证 + 8 卡齐亮 + 首页优化（W6）→ FLORA 对齐批（2 天，ADR-051）+ 对话工作流批（B1~B4，6 天，ADR-052）+ 消耗计算大迭代含支付/积分架构（W7）→ 运营端质量飞跃（W8-W10，内容生产中台 / Memory + 账号体系 / 端到端联调三刀）→ 支付实际开发与分发联调（W11）→ 法务与 AI 合规（W12）+ 缓冲续项（W13）+ go/no-go 评估（W14）**；**2026-08-31 FLORA 对齐批插入 W7 头部 2 个工作日，其后全部顺延——go/no-go 10-23 → 10-27（回退 10-30，不触发新拍板）**；**2026-09-03 对话工作流批（B1~B4，ADR-052 + 母文档 `DIALOG_WORKFLOW.md`）插入 W7 即日动工 6 个工作日（09-02 实际交付 ADR-051 续裁定批，消耗计算未动工）——原计划自 09-02 起顺延 7 个工作日；W9「意图识别智能化升级」并入 B2 交付（同一意图面），W10 起净顺延 6 天——go/no-go 10-27 → 11-04（⚠️ 超已批回退位 10-30；回退路径 = W13 缓冲吃 3 天回到 10-30 内，或 W9/W10 压缩，下次周五滚动定夺）**；**2026-09-05 拍板（三）**：对话工作流批余量（B2 day2 / B3 / B4×2）提前全部完成（记 09-04 交付），**积分系统批（ADR-055，母文档 `docs/BILLING.md`——积分完全先行、真账本、支付只留 W11 边界）提前开工**——当日实际 09-03~09-05 三天完工（原排 09-07~09-11 五天），"09-07 开工"安排同日作废、窗口由拍板（四）支付批顶上；**2026-09-05 拍板（四）：支付批自 W11（10-02）提前至 09-07 开工占两周（09-07~09-18）**——W8~W10 运营端顺延一周（09-21 起），W12 起因运营三刀原状（W9 四天 / W10 周五起）恰好落回原排期，**go/no-go 维持 10-29 不动**（仍早于已批回退位 10-30 ✅）；代价 = 支付商入驻审批跑道收紧（08-14 提交 → 09-01 前须确认沙盒到位，未过审首周切 mock 对接、真联调吃批内第二周）；**2026-09-06 拍板（五）：全流程测试批插入 09-07~09-09 三天**（含积分计算验证——hold→capture→release 对账 / 估价贴 vs 实扣 / 负余额路径 / 孤儿 hold 缺口 P1 复验），**全部后续排期顺延 3 个工作日**——支付批 09-10 起（09-10~09-23），W8 09-24 起，**go/no-go 10-29 → 11-03**（⚠️ 超已批回退位 10-30；回退路径 = W13 缓冲吃 3 天回到 10-30 内，或测试批提前完工自动回位，下次周五滚动定夺）；**2026-09-07 拍板（六）：图内核重建批（ADR-057 图即产品对象 + 简报 `archive/tasks-done/graph-as-product.md`，原型 `scratch/node-ux-proposal.html`）插入支付批之后、W8 运营端之前（09-24~10-07，10 个工作日）**——积分展示面讨论牵出真伤口：没有一个确定的 node 交互方式就无从做好积分系统，且修订环在产线带伤（修订 run「Target clip not found」实证）；三平台（ElevenLabs / Flora / MiniMax）对照核对出共享图内核（node = 纯函数 / prompt 在卡面 / DAG 先展示后运行 / chat 布线），我方「图 = 编译即弃产物 + 五补丁投影」模型翻案为**持久可变图 + wiring 层（chat 唯一消费面，能力完备手势缺席）+ 草稿态（先图后运行）+ 节点五型 + 端口法则 + prompt 直改+确认 + 投影层火化 + 语义账本塌缩**。施工两站：首站 = 图持久化 + wiring 最小集 + **现有管线迁移上图**（修订环根治），第二站 = 生成类配方孤岛生长。**W8 起全部顺延 10 个工作日**——W8 10-08 起，**go/no-go 11-03 → 11-17**（⚠️ 超已批回退位 10-30 十二个工作日；回退路径 = W13 缓冲吃 5 天回到 11-10 + 内核批第二站让位 W8 并行 + W8~W10 三刀压缩，下次周五滚动定夺）。**执行内核零改动承诺**：compile DAG / NodeBase 四算子 / 队列 / hold→capture→release 全部保留——本批是图的所有权与展示层重建，不是执行层重建。施工依据：闭环优先于卡片数量（ADR-035/041，简报 `archive/tasks-done/results-canvas.md`）；FLORA 对齐依据 ADR-051 + 简报 `archive/tasks-done/flora-parity.md`；对话工作流依据 ADR-052 + 母文档 `docs/DIALOG_WORKFLOW.md`；积分系统依据 ADR-055 + 母文档 `docs/BILLING.md` + 简报 `tasks/credits-system.md`；运营端排期承接 ADR-042 / 母文档 `docs/POSITIONING.md`；积分批承接第二周 P4 估价地基（`workflow_steps.estimate`）。工期按全栈排实：前端与后端双端各占工期，界面留出反复校准时间，调研 spike 与 e2e 测试显性占行。**2026-09-14 会话层工具 loop 批 + decompiler 批插入 09-14 周（ADR-077/078，与画布三族批并行跑道），其后各周次整体顺延一周（go/no-go 相应顺延一周，具体日期周五滚动时落定）**。

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
| **第十一周（09-10~09-23，自 10-02 提前）** | **支付实际开发 + 分发联调**——支付接入（沙盒；**入驻审批跑道收紧 ⚠️**：08-14 提交 → 09-01 前须确认到位，未过审首周切 mock 对接、真联调吃批内第二周；钱→积分购买比例与套餐语义本周定）+ 订阅生命周期 + webhook + 套餐权益执行 + 用户计费中心（积分台账投影）+ LinkedIn / TikTok OAuth 发布链路（开发者权限到位 ⚠️） | 🎯 商业化闭环 + 分发就绪 |
| **图内核重建批（09-24~10-07，拍板（六））** | **图即产品对象（ADR-057）**——`graph_nodes`/`graph_edges` 持久图 + wiring 层（add_node / connect / edit_prompt / delete_node / run(_subgraph)，chat 唯一消费面）+ **现有管线迁移上图（修订环根治，首站）** + 草稿态（先图后运行、逐节点估价）+ 节点五型卡解剖（caption 右槽恒空 / 卡面 prompt 区 / factsbar 外置）+ 端口法则 + prompt 直改+确认 + 投影层火化（runFlow 五补丁退役）+ 语义账本塌缩 | 🎯 修订 = 图变更（「Target clip not found」类伤口根灭）+ 画布直读零投影 |
| **第八周（10-08~10-14）** | **运营端（上）：内容生产中台**——选题库（topics + lifecycle + agent + 选题卡发射）+ 内容形态库（分镜 / 脚本 / 预设 / 文章）+ 不同平台 skill 添加（**R5 虚拟视频作为 AI 生成 skill 落位**，ADR-026） | 内容生产中台通路 |
| **第九周（10-15~10-20）** | **运营端（中）：Memory + 账号体系**——Memory（persona）模块迭代（风格学习 + 校准回路 + Voice DNA）+ Persona 显化深化 + 账号体系绑定（**positioning root**：`personas`→`positionings` 改名刀 + 三分区 + `channel_accounts.positioning_id` + 公共档案）+ 定位对话化（意图识别智能化升级并入 W7 对话工作流批 B2） | 🎯 身份复利资产就绪（persona 校准回路 + 渠道有所属） |
| **第十周（10-21~10-27）** | **运营端（下）：端到端联调**——home 改版（回访态 = 选题管道 + 最近产物 + 渠道状态）+ 全链联调（定位 → 选题 → 生成 → 精修 → 发布）+ 闭环质量验证（多 persona × 多选题组合） | 🎯 **运营端闭环 + 质量飞跃** |
| **第十二周（10-28~11-03）** | **法务 + AI 合规**——法务页面 + 用户协议 + 隐私协议 + Cookie 同意 + AI 内容标识（C2PA 选型 + 自动判定 + 披露）+ SEO + 邮件送达 + 监控告警 | 法务 + 合规 + 上线配套就绪 |
| **第十三周（11-04~11-10）** | **缓冲周 + 续项收口**——性能压测 + 文档收口 + 回归全套 + Last-mile 修复（W11 入驻审批 / 开发者权限未到位时的回退位） | 上线前提全部到位 |
| **第十四周（11-11~11-17）** | **全周期验收 + go/no-go 评估**——九阶段成果整体走查 + 修复 + 上线演练 + 🎯 go/no-go 评估材料 + 全周期进度回填 | 🎯 上线 go/no-go 评估材料（**11-17**） |

> **闭环优先于卡片数量（2026-08-05 拍板）**：配方卡全部点亮但不闭环时，期中汇报只能说"还没跑通"；先立闭环——闭环链于第二周收口，dub 为全程载体卡；此后每张新卡 = 一行"扩展配方类型"，上线即落入既有通路——叙事从"补窟窿"变成"扩展通路"。哲学论证 → STRATEGY §5；行为规格 → CHAT_ARCH §3.3；形态裁决 → ADR-035/041，简报 `archive/tasks-done/results-canvas.md`；配方数据 schema → RECIPES §7.1。分镜压缩 1 周 ⚠️，回退则 go/no-go 移至 10-30。闭环链全部图面由 **FlowView 只读图基座**渲染（ADR-036）——overlay 扇出主视觉 / 结果画布 / 血缘板（复核门），chat 唯一修改通道不变；并直接消费架构迭代红利（ADR-039）：画布节点自动获得友好名，配方卡的流程图与真实执行自动核对、图不骗人。

**外部因素（需按期启动）**：LinkedIn / TikTok 开发者权限（暂缓，时间未定——支付批（09-10 起）联调届时按实际申请时间重排）；支付商入驻申请（08-14 前提交，审批周期数周——**支付批 09-10 动工前提 ⚠️ 跑道收紧：提交至动工 ~4 周，09-01 前须确认沙盒审批到位；未过审则首周切 mock/合同流对接、真联调吃支付批第二周**）；律师法务联系（08-24 前启动，周期 2–4 周——W12 法务落地前提）。术语表、管理后台、帮助中心等最后项按需再考虑。

> **W1~W7 周次实记、三个已完成插入批（全流程测试 / 画布三族 / 会话层工具 loop+decompiler）与 W11 原排期残留**已归档至 `archive/PROGRESS-2026-cycle1.md`（2026-09-17）；下方仅保留未来周次（W8 起）。

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
| ~~质检节点（单产物 + 全片，verify = 节点 kind）~~ | — | — | **已合并至产物质量线期 3（08-23 落地，ADR-047）**：verify 节点全量接线 + 确定性检查矩阵 + QualityBounce + best-not-last 快照回退 + 双败路由（fidelity→needs_human / craft→dock escalation）——条目关闭 |
| 结构化节拍图 + clip-spec motion 枚举 | P2 | 覆盖问责（✅）；限 video 源 crop 动态预设，落地需新 ADR 明确与 stills Ken-Burns 拒绝的边界 | STRATEGY §2.5；与智能分镜线（第三周）汇合评估 |
| 去静默 / 去口头禅 | P2 | 词级时间戳（✅）；随 editor 一键操作方向评估 | 矩阵 §B（2026-07-23 下放：演讲密度低 + 跳剪伤专业感） |
| LLM provider 抽象 | P1 | ADR-025 已决（薄接口）未实施；触发 = EU 客户要求 Mistral/EU-hosted | 2027 架构（MODULE_ARCH §4.1）。UX 形态定调（2026-08-02）：用户-facing 是**策略开关**（如"优先 EU 托管模型"），不是模型 SKU 货架（对照 Lovart 模型选择器，否决）；composer 模型 pill 已退役（2026-08-22：管线按模态分派 provider，pill 无法诚实展示终值）。实施第一纪律 = **边界规范化**（dsh defensive-patterns「公共约定两侧都要遵守」：provider 的多种失败形态在边界单态暴露，消费方永不猜异常来源，`research/deepseek-harness.md` §3） |
| 字幕翻译 + 校对视图（side-by-side） | P1 | 多语言输出（✅） | 矩阵 §G |
| 多语言文案质量（Voice DNA 跨语言保真） | P1 | 术语表（下方可选需求） | 矩阵 §G"极高"；STRATEGY 牌 4 |
| 产品度量地基（漏斗埋点：上传→生成→精修→发布→回流） | P1 | 无 | 审计 2026-07-22；文档坑位 METRICS.md（README 已登记） |
| 一回合多交付（user-facing checkpoint 通道，ADR-085） | P1 | ADR-084 言语语义管线（✅ 09-17）；感知族读工具（✅ T2b） | 2026-09-17 拍板**同日施工落地 + 评审四点收口**：① 命中率验证义务——主路径单读直出结构性零 checkpoint 非缺陷（判断句住终答），实测系统性过低才重审路由；数据面 = `tool_loop_checkpoint` 日志 + S21 探针 ② iteration-0 豁免 = 防御兜底非产品行为（纯套件锁定）③ checkpoint = live delivery 非 durable——回合失败随事务回滚，第一版不扩事务模型 ④ eligible 资格纪律常驻。验证待用户自跑（纯套件五条路由用例 / prompt gate / S20B+S21） |
| 真实 Gallery（公开项目流入 + remix） | P2 | 配方卡点亮相续（字幕卡 / 图文视频 / 分镜双子卡 ✅ 均已点亮；画廊 v2 八卡批次窗口待指认，ADR-048）；projects/outputs 公开性字段须先 MODULE_ARCH §4 登记 + ADR | STRATEGY §5 Phase 2；配方=数据 schema（RECIPES §7.1）使"用户发布的可 remix 项目"可直接序列化为同款数据包 |
| 虚拟视频卡（画廊 v2 出列） | P2 | R5 作为平台 skill 落位（W8 运营端上）+ 真实成对示例可烘焙 + 两级闸门重过 | 2026-08-23 画廊 v2 拍板（ADR-048）出列：趣味/实验定位过不了闸门① 场景真实性（知识专家的高频真实场景是把已有素材变成内容，不是生成虚拟分身）；出列 ≠ 否决——R5 作为 AI 生成 skill 在 W8 不同平台 skill 添加批次同批落地，管线就绪且能拿出真实成对示例后按 RECIPES §4.8 重新挣座位 |
| 使用示例跑一遍（demo 素材试跑） | P2 | 配额成本控制形态（试跑限次 / 免费额度内抵扣）；demo 素材已在桶（✅ `demo/uploads/demo_talk.mp4`） | ElevenCreative 配方 modal "使用此示例"证据（2026-08-08）：访客零上传以烘焙 demo 素材试跑配方，增长向入口；试跑 = 同一 chat 主线（配方播种 + 自动 Start），非独立通道 |
| 模型 EU-hosted 选项（Mistral 等） | P2 | provider 抽象（上行） | 2027 架构 |
| 渲染服务源站限速韧性 | P2 | 无 | 2026-08-10 渲染回归排查：Remotion 内部 asset proxy 的服务端 fetch 不走系统代理，本机直连 TOS 被限速（~110 KB/s）时取帧超时全盘皆输；当前缓解 = 渲染进程带 `HTTPS_PROXY` 环境变量；长期项 = 源下载落盘再渲染 或 renderer 显式 proxy dispatcher |
| persona 精修 chat 化（per-field 再提炼 + merge 语义 + 单一对话微调入口） | P1 | 人设页渲染重构（简报 `archive/tasks-done/persona-style-panel.md`，第二周顺做）；一面一 MentionEditor（✅ 08-11） | 2026-08-13 外部评审建议（经闸门过滤）：现状 `generate` 全量重写覆盖用户手改，per-field 再提炼必须带 merge 语义（手改保留，对齐 chat 恒胜原则）；对话微调 = persona 级**一个**入口，禁每模块一个气泡；定位根重构（ADR-042）落地后入口改挂定位的人设分区 |
| persona AI 印象摘要字段 | P2 | persona 提炼链（✅ `POST /personas/{id}/generate`）；摘要进 `PersonaContext` + 表列 | 同上来源：概览卡顶部"一句话画像"。无摘要版概览卡（现有字段拼装）已随渲染重构落地，本条目只补 AI 生成的那一句 |
| ~~配方示例片画幅跟源~~ | — | — | **前提消解，条目关闭（2026-08-23，ADR-048）**：画幅 badge 随画廊 v2 退役——卡面不再承载任何输出形状声称（封面 = 工艺示意图），承诺句与 overlay 示例 tab 的真实成对示例自带真实比例呈现，"示例片标画幅"无落点 |
| insert_broll 技能（layers 家族第一个技能住户） | P1 | 轨道模型 layers 契约（08-17~18 批，ADR-044）；`slide_pages` 已在跑（✅）；排在 reframe spike 结论之后 | 2026-08-17 语录评审：「我讲到增长数据那块，画面切到我的幻灯片」——知识专家最强的 B-roll 场景（自己的幻灯片/截图）；原缓议理由只覆盖 stock B-roll，排期理由修订在案。全链拆解归简报 `archive/tasks-done/track-model.md` §7.3（LLM 只做语义定位，机械工序选页+取窗 → layer 条目） |
| SSE 收官散文回合 | P2 | 无（run 收官钩子在） | 2026-08-17 语录评审⑥：打勾流 recap 之外追加一个 assistant 收官回合（"做好了 3 条短片，第 2 条最强因为……；下一步建议：……"）——一次调用，是"到来即彷徨"用户的闭环接住点（STRATEGY §5）；不是进度（不违 ADR-041 打勾流唯一进度面），是收尾 |
| 素材理解前移（director_understand 挪上传时跑） | P2 | 素材级 + asset-hash 复用已在（✅） | 2026-08-17 语录评审①"计划层对素材盲"的正解；代价 = 每次上传烧一次 LLM（哪怕素材从没被用）——折中版（transcript 首段摘录进上下文装配）已挂第三周 08-21 stretch；**完整版 2026-08-22 汇合产物质量线**：理解层 v2（节拍地图：climax/emphasis 双信号/quotables/topic boundaries/visual anchors，上传时跑 + asset 级复用）即本条的兑现形态，见 `archive/tasks-done/output-quality-line.md` §2.2；~~已排第五周~~ **✅ 2026-08-23 落地（随期 1，验收三件套过）** |
| landing 叙事骨架重构（六幕 + 商务尾） | P2 | 配方真实产物密度（FlowView 精致度包 ✅ 08-19 已备）——存量不到位撑不起证据铺满的骨架，缓做裁定不变 | 六幕结构 2026-08-20 收敛：`LANDING.md` §4 P2 骨架条（幕表 + 商务尾 + 背书插槽 + 文案纪律）；原始证据 `research/flora.md` §2 |
| reframe per-clip 检测缓存 | P2 | speaker_map 素材级事实（✅）作缓存源 | reframe 线四轮评审遗留（2026-08-19 周评审补登记）：reframe 节点每 clip 启动重探测（~2.5s/clip），同素材多 clip 重复付费，speaker_map 结果可复用 |
| morph 罕见拓扑双渲染 | P2 | 无 | 同上：non-fork→fork→non-fork 的无 producer 链形下，抑制与 rescue 可能双付一次渲染（exotic，perf 项） |
| pre-fail rescue 步骤标签纠偏 | P2 | 无 | 同上：rescue 重挂的 render 步骤行误标 "skipped: upstream failed"（纯展示错，产物正确） |
| reframe phase-2 残毫秒竞态 | P2 | 无 | 同上：检测窗内并发编辑经增量重放已大幅收窄，仍存毫秒级残口 |
| undo 重挂的陈旧 MP4 处置 | P2 | 产品拍板 | 同上：undo 触发重渲染后旧 MP4 仍挂产物行（OpsCard 侧留有死代码）——清还是留，待产品裁决 |
| 编辑器 staleness 模型统一 | P2 | 无 | 同上（既有类，非 reframe 批引入）：编辑器对 run 中途变更的感知模型 |
| 定点 reframe 报价虚高 | P2 | 无 | 二轮冷审（2026-08-20）：reframe_clip 的 estimate 对全项目 clip 求和而非 target_output_id 目标集——纯展示，不阻塞 |
| 字幕简繁归一跟 target_language | P2 | 无 | 评审（2026-08-20）：whisper 对台湾腔国语源出繁体字幕（競爭/協同），LLM 标题按 zh 写简体（竞争/协同）——同帧简繁混排在 demo 里可见。字幕层按目标语言做简繁归一（ASR  verbatim vs 展示一致性的取舍先拍板） |
| agent 调用台账（agent_calls 落库） | P1 | 无（Model/Agent 单边界与计量捕获点在） | 2026-08-20 DeepSeek Harness 评审（`research/deepseek-harness.md`）：assistant/message 纪律——每次 provider 调用（含空内容 / max-tokens / 校验失败的首试）都是落库事实，usage 永留；我们现状只记钱（cost），修复一轮不留痕，harness 质量信号（修复率 / schema 失败分类 / prompt 版本回归）与失败取证全丢。**2026-08-22 质量线补三信号 schema**（`archive/tasks-done/output-quality-line.md` §2.6）：过程信号（repair 轮次 + diff 幅度）/ 机制信号（质检违规类型分布）/ 地基真值信号（用户 edit-ops 按节点归因——欠交付节点靠它指认）。台账 = ADR-025 计量纪律从「钱」扩到「调用事实」（agent 名 / run+step / attempt / outcome∈ok·repaired·failed·empty·max-tokens / tokens / 错误类 / prompt 模板名）+ **取证级**：调用 envelope 可重建（渲染后 prompt / schema / 装配上下文哈希，大 prompt 走对象存储 spill——model-visible ⟺ logged 的账簿形态；行业座位 = Agno Traces），挂第十一周成本校准闭环做前置；动工时补 ADR |
| 闸门编目（invariants 登记表） | P2 | 无 | 同上评审（dsh invariants 子系统）：偷编目不偷框架——闸门家族（出生地 ∀ 校验 / 启动自检 / 运行时数据闸：撤段序单调性、harvest 带因即拒、叙事闸）散落无名录、按事故逐个加；一张登记表（名字 / 位置 / 统一拒绝形态）让全家一眼可查、可 grep、可进文档。补两条深设计：**explained-empty**（无闸模块须写 `No runtime invariant: <原因>` 式显式说明，防「忘了闸」盲区）+ **闸只断言自有数据关系**（事件流 / 可变数据的关系，绝不断言服务或方法存在性） |
| LLM 录制回放层（MiniMaxClient 边界 record/replay） | P2 | agent 调用台账（上行，同边界同批可并） | 同上评审（dsh `llm-replay` 包）：适配器 seam 录制真实 provider 流成 fixture，无密钥确定性回放——代码侧漂移变确定性回归（注册表扰动的零假设测试从此免费）、PR 可审 transcript diff；全真剧本测试 保留做行为探测，分工 = dsh snapshot（无密钥） vs test:e2e（带密钥）格局 |
| 执行中自适应重规划（interrupt + 重 authoring） | P1 | interrupt 节点（✅）+ 任务书 refine 链（✅）；与素材理解前移（上方 P2 行）互补，agent 调用台账（上方 P1 行）供取证 | 2026-08-20 拍板必做：run 中途节点产出的事实与任务书假设矛盾（ASR 检出素材语言 ≠ 任务书语言、素材内容与预期不符等）→ 自动 interrupt + 模型重 authoring 一版任务书，diff 确认后续跑——人在环重规划，**非 tool-loop**（常备否决不翻案）；预计 2–3 天，排期窗口待指认（建议台账前置之后；插入周内需指明替换项）。**2026-08-22 两轮外部评审三源背书 + 路由判据落地**（ADR-047 重规划边）：质检失败的机械路由——修复所需信息不在理解层 schema / 超出单节点参数域 → 交还意图层重规划；retry 不中自动升级；素材级不足走诚实降级（不假造钩子）。模型驱动编排翻案被三源独立否决，否决边界明文化（模型编排 = 禁；节点内有界环 = 合法） |
| EU AI Act 内容标记（"AI Generated" 默认开 + 设置可关） | P2 | 合规立场实装（合规包本周期外）；标记形态 = 渲染/导出期，不依赖发布通道 | ADR-046 登记；MiniMax 水印弹窗先例（`research/minimax-design.md` §2：默认开 + 告知去哪改 + 唯一主按钮）；EU AI Act 偏好项 `research/flora.md` |
| ~~产物质量线（理解层 v2 + 剪辑师层 + 质检环 + 钩子预览闸）~~ | — | — | **质量线期 0-3 全部代码级落地，期 4 整套退役（ADR-049，评审回 chat）——条目关闭。** 归因 = 缺层（storyboard→clip-spec 之间无 timeline 创作者）+ 缺环（无质检回看）+ 缺尺（无质量度量），DAG/工具纪律零推翻；施工顺序 = 尺子先行（ADR-047）；证据表 `research/craft-anatomy-2026-08-22.md`；简报 `archive/tasks-done/output-quality-line.md`。后续质量控制沿 verify 节点 + best-not-last + QualityBounce 三件套在生产层常态运行，不另立条目。 |
| TRANSCRIPT 资产生产侧语言印记 | P2 | 无（消费侧已在：`_project_source_language` 读 `meta.language`，08-28 P2 扩展至 TRANSCRIPT） | quote-cards v3 P3 烘焙登记：视频/音频由 ASR 盖 `meta.language`，文本族 processors（transcript / docx / pdf 上传链）不盖章——alt 推导对纯文稿项目缺源语言锚（烘焙脚本手工盖章绕过）；盖章点 = 各 text processor 完工处（语言探测或上传者声明） |
| verify judge QuoteReadability schema 回归 | P2 | agent 调用台账（上方 P1 行——outcome 分类天然承载此类回归的取证） | 2026-08-28 两轮烘焙 2/2 命中：MiniMax 对 QuoteReadability 出 per-quote 裸数组（`[{quote, context_read, standalone, issue}, …]`），pydantic 期 object，schema repair 一轮仍败，`verify_judge_failed` 后 verify 降级完成（产物不受影响，judge 信号缺失）；修法 = prompt/schema 对齐或裸数组→wrapper 边界归一 |
| S41 media_text_fallback × repair 组合漂移 | P2 | agent 调用台账（同上——funnel 行为的取证面） | 2026-08-29 全套件跑红揪出（main 上既有，非 quote-cards 轮引入——base.py 与断言自 HEAD 起均未动）：S41 7a 期"media 降级在 attempt 内部完成、不吃 repair 轮（pre-echo）"，实际 schema 拒绝直接烧掉 repair 轮且媒体未降级（payload 仍 parts 表 + 带回显）；生产两处 `media_text_fallback=True`（clips agents / registry:91）在册；修法 = base.py 降级时机回 attempt 内，或断言改述现行为 |
| ~~孤儿 hold 回收（project 删除即解冻 / reaper）~~ | — | — | **✅ 09-05 当日兑现（P1 不跨夜）**：删除端点同事务退未结 hold（非 RUNNING）+ 收官路径台账自结算（`_release_orphaned_hold`，run/项目已删双路）+ `finalize_stuck_runs` 大小写潜伏 bug 修复（`'RUNNING'` 死匹配从未生效）；剧本 S15 锁删除路径（RUNNING 在途归 worker 收官）；dev 存量 7 笔按业务决定不手工补（尺子 ○ known-open 豁免）——条目关闭 |
| ~~对话工作流升级（B1 改名批 + B2 brief 账本/ask + B3 预填评审卡）~~ | — | — | **已排期（2026-09-03 拍板，W7 即日动工 09-03~09-08，ADR-052）——条目关闭** |
| ~~research 节点试点（有界 loop 节点，B4）~~ | — | — | **已排期（2026-09-03 拍板「立即」，随对话工作流批 09-09~09-10）——条目关闭** |
| 步骤级 LLM 命名（per-task `name`） | P2 | 展示文案二源律（✅ ADR-058，09-09）——run 级 name 已通，本行补 step 级 | **09-09 拍板「下批就做」**（排期窗口待指认）：09-09 用户判词的全量形态「tasks 的步骤也是 LLM 命名就没有文字核对问题」；本批 `taskLabel` 链推导已收窄为回退 + 手改撤名已落，步骤名全量 LLM 化 = name 进 TaskItem + builder 钢印位 + RunTaskList/打勾流读法 |
| stub 塌缩（"No source material" 行） | P2 | 无 | 09-09 同批挂账：无素材 writer-only run 的 stub 行应塌缩不渲染 |
| mobile OutputChatCard 核对 | P2 | 无 | 09-09 同批挂账：focus 退役与 runTitle 章名后移动端产物卡读法一致性核对 |
| MG 动画工具（generate_motion_graphics 类） | P2 | 画布三族批两站机制（批 A3）+ clip-spec `motion_graphic`/`text_callout` 元素枚举（已在 schemas.py）+ Remotion 渲染面 | 2026-09-14 ChatCut 参照拍板：「AI MG动画，生成后还能继续改」= 两站模式第三次复用——MG 脚本（type=table × prototype=manual，行 = 场景：时间窗+文案+动效说明）→ MG 成片（video×generator）；「继续改」= 文档站文字层直改→重渲染（零再生成的理解重买）或 chat 修订→版本分页；画布架构零新增 |
| 对话剪辑工具族（cut / stitch / reorder —— ChatCut「AI 视频编辑器」方向） | P2 | 三族批落地 + L3 铁律边界复核（铁律管的是我们自建编辑 UI 的多轨时间线，不管 agent 能力；专业需求仍导出剪映/Premiere） | 2026-09-14 ChatCut 参照：「用对话来剪辑你的视频」= video×editor 节点 + chat 修订循环（修订 = 原地图变更现成）；缺的只是工具注册表里的剪辑 tool，不是画布架构 |
| 能力画廊 generate/edit 分组徽标 | P2 | 三族批 prototype 属性落地（批 A3 C2b） | 2026-09-14 词表评审（ElevenLabs/ChatCut 参照）：generator/editor 轴的产品显性化座位 = 配方画廊分组 / 卡片徽标（读面派生：有媒体入边 = editor），永不是节点 type；Ele 的媒介 tab 同法可从注册表派生 |
| quotes/carousel 两站拆分 | P2 | 三族批两站机制（✅ 2026-09-14，translate/dub 先例） | 三族批简报 §7.3 遗留（简报 `archive/tasks-done/graph-canvas-three-families.md`）：quotes/carousel 现单站 image×generator——拆「文案稿 doc 站（table×manual）+ 图装配站」同款两站，改文案零重买图渲染（billing 对账可见 renderer capture 为 0） |
| 样式覆写 UI | P2 | 三族批 editor 卡程序区（✅）；`style_overrides` JSONB 地基未落 | 三族批简报 §7.3 遗留：装配节点 `style_overrides` 数据层 + 用户面（杠杆行形态归批 B4 一并设计；皮肤六件之外的 run 级覆写） |
| 分镜表表格档节点（rev 迭代） | P2 | 三族批表格档先例（✅ 译文/配音稿两站）；编辑映射 op 设计 | 三族批简报 §7.3 遗留：plan 的分镜产物（槽位 + 覆盖理由）持久化为表格档节点（transcript 与 clips 卡之间），删行 = 弃选 / 改时间窗 = 重切 / 改论点 = 重选——全部确定性 op；用户原话挂头 |
| 能力缺口喂给（decompiler gaps → 需求池候选） | P2 | decompiler 骨架（✅ 09-15，ADR-078 判词②）；缺口观察积累后再按价值排期 | T5 落地登记：拆解时契约无座位的字段 = 诚实「做不到」清单（CraftGap）；`unsupported` = L3 线永不承诺，`not_yet` = 契约座在、写手未到——**not_yet 族即本池候选源**（既有对应行：text_layers → MG 动画工具行；broll_overlay → insert_broll 行）；旅程二 2b 的带理由纠偏消费它，运营侧按观测频率升格排期 |
| Turn budget = iteration cap + wall-clock deadline | P1 | 交互完整性批 A+B+C（✅ 09-17）——turn_state 状态机与准入门在 | 2026-09-16 事故归因挂账（GPT 判词D）：`max_iterations=6` 只封次数不封时长——多轮 quiet read 把回合拉到 60s+，是 abort/超时暴露面与 trigger 竞速窗的放大器；到期的诚实降级形态（cannot-do 行 / "仍在处理"提问）随施工拍板，不借本条开启 AgentBudget 大架构讨论（North Star 触发制不变） |
| turn 级事件可观测性落库 | P2 | agent 调用台账（上方 P1 行——同取证面，天然合批） | 2026-09-16 事故死因不可考的根：stdout 日志不持久 + 回合中途死亡零痕迹；turn_state 已有 in_flight/failed 两章，本条补的是「为什么死」（拒绝轨迹 / 异常类 / 耗时剖面落 DB，非日志文件） |
| ~~单一叙事者收口（pending-plan 静默 + 语言唯一 owner）~~ | — | — | **✅ 09-17 当日兑现（ADR-080）**：pending task_book 静默谓词 + `conversations.ui_language` owner 列（migration h7d1e4a93b26）+ `_trigger_language` 改读 owner 链；纯函数套件锁链序——条目关闭 |
| ~~选项语法统一（chip 退役 + OptionDock 编号 1/2/3）~~ | — | — | **✅ 09-17 当日兑现（ADR-081，阻塞形态拍板 = 阻塞式）**：`WrapUpArgs` 收窄纯 label、review 行 dock 真实编号选项问、answer generic 分支按 run 状态分派（无 run 走 plan path）、徽章 a/b/c→1/2/3、存量 pill 行读容忍——条目关闭 |
| 画布可读性②（同族链分组 + 长边路由 + 居中） | P1 | ① 高度失真 **✅ 09-17 已落**（ADR-082 判词①——`layout.ts` settled 分支空气压缩：同列按当前渲染高堆叠、`min(serverY, …)` 结构保险、服务端帧零改动）；`GroupFrames` 组件现成（配方说明书先例） | ADR-082（2026-09-17 拍板）：呈现/语义隔离铁律——禁为排线造语义节点；本行剩余 = 同族链分组（项目页补传 groups）/ asset→asm 跨列长边路由 / settled 路径居中；验收同 5 秒三问。**2026-09-18 起由 Product Flow Alignment Batch C 吸收施工**（合同 `tasks/product-flow-alignment.md` §7；layout 错位 root cause L1-L5 归该批，本行三残留随批吸收或拆分回登） |
| ~~信任锚 echo（素材理解的发言席位）~~ | — | — | **✅ 09-17 当日兑现（ADR-083，价值链追踪 + GPT 三收紧全采纳）**：present_plan echo 2 句律修订为三语义职责（判断/转述/完成+下一步，约束语义不约束句法）+ grounding 四级证据链（metadata 仅身份证据）+ assemble 期注入 ready 理解行（零 LLM 零轮次）；single writer 不动——条目关闭 |
| `select_clips` 存留范围裁决（ADR-PENDING） | P1 | ADR-089 实施批开工 | 旅程四拍 6 挂账（ADR-089 §8 登记）：plan 来源的工作里 pipeline LLM `select_clips` 萎缩为确定性裁剪——发现工作移至 chat 边缘 agent，pipeline 更确定、报价更准；候选存留面 = 长素材二次裁切 / 语义连续处理 / execution-time transformation；实施批开工第一件事裁决，不提前封口 |
| 深度 reviewer / 看片复核 | P2 | 视频理解 provider 能力与成本评估 | 旅程四 B7 挂账（ADR-088 §8）：reviewer 现界 = 确定性 verify + plan 意图比对；「看片复核」（渲染产物内容级自检）缺稳定 ground truth 与成本模型，需求观察后再评 |
| 常驻自主拨盘（standing autonomy dial） | P2 | R1.1 商业形态（订阅 / 额度信封） | 旅程四挂账 B6：Claude Code auto-mode 参照——常驻授权信封（如「N 积分内自动确认」），费用语义在设定信封时一次性披露；ADR-087 D1 刚退役 review 档不重开，商业形态明朗后随 R1.1 评 |
| Canvas 密度组织学（journey 分组 / 折叠 / 归档） | P2 | 旅程四实施批（R24 `journey_id` 身份落地 = 前提契约，ADR-088 §10） | 旅程四拍 10 挂账：活跃项目多旅程后画布节点密度（候选合集 / 精选 / 方案 / 产物累积）——分组 / 折叠 / 归档的呈现层方案；禁为组织造语义节点（ADR-082 呈现/语义隔离铁律同律） |

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

- LinkedIn / TikTok 开发者权限：**暂缓申请（2026-08-05 拍板，时间未定）**。需以公司主体申请、审批周期数周；双平台代码已完成。第十三周联调排期届时按实际申请时间重排。
- 支付商入驻审核：08-14 前提交申请，审批周期数周。
- 法务文书：律师外部产出，周期 2–4 周，08-31 前启动联系。

**需要拍板的决策点：**

| 决策 | 需要谁 |
|---|---|
| 支付商选型（欧盟 VAT 由平台代处理 vs 自建税务）与入驻启动 | 总监拍板 + 工程调研 |
| 目标上线日（go/no-go = **11-17**——2026-09-07 拍板（六）图内核重建批（ADR-057）插入 10 个工作日，自 11-03 顺延 ⚠️ **超已批回退位 10-30 十二个工作日**；回退路径 = W13 缓冲（11-04~11-10）吃 5 天回到 11-10 + 内核批第二站让位 W8 并行 + W8~W10 三刀压缩，下次周五滚动定夺；W13 缓冲仍消化入驻审批 / 开发者权限等外部依赖） | 总监 |
| 律师人选与预算 | 总监 |
| 结果画布转正复核（ADR-041；周五 08-14 小白复述测试，不过则网格回退默认中心） | 产品 |
| 定价套餐的业务输入（档位 / 免费额度 / 计价形态） | 总监 + 业务侧 |

---
