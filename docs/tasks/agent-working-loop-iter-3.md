# Agent Working Loop 迭代三：持续工作闭环收口——修订回路 / 收官审计 / 过程可见 / 记忆窄切 + 迁移弧裁决

> Status: **代码面收口（2026-09-23）——live 验收待用户六拍走查**（`scratch/iter3-six-beat-walkthrough.md`；全顺后简报归 `archive/tasks-done/` + edit_graph 退役小提交）**——Product Gate 已拍板（同日）：产品母线 = Discover → Select → Plan → Confirm → Execute → Review → Revise → Discover again 持续工作闭环；四点收口（停顿合同语言 / 决策包可编辑律 / 自治修 P2 / Memory 三分拆）已并入 §1~§2 冻结条。工程拍板 E1~E10 已生效（同日，全部按 §3 推荐答案：E1 CompiledScope 返回对象 / E2 快照 plan_task_map / E3 mark_compiled+supersede-继任双态写者 / E4 revise_output chat 专用终态 / E5 exemplar 事实行注入 / E6 R25 窄门砍出本批 / E7 活动帧只扩 at+duration_ms / E8 chat loop 预算 12 / E9 剧本座 S-explore-3/4/5 / E10 N-58 词族先行）。施工进度：S0 ✅（`1dce4c4` N-58 登记 + ADR-089 §8 select_clips 裁决销记 + PROGRESS 池挂账）；S1 ✅（`bf4d771` CompiledScope + plan_task_map + mark_compiled/supersede_plan + route_revision，纯 pytest 546 绿 + check_gates OK）；S2 ✅（`fa336d1` 共享编译座 `chat/exploration_compile.py`（preview id 带项序防同 select 撞键——纯测试实测修复）+ plan_turn 两座机械换基 + ChatTurn 探索族座位 + dock 扩件 plans/plan_task_map/derived/persona_id + chat_intent_system.j2 发现型判定段 + context.py 探索行标签 + loop 预算 12；纯 pytest 557 绿（+11 新件）+ prompt_gate 五探针全绿（A/B/C/D 12/12 满带，新探针 E = post-run 发现型 chat 路形态，实测带 9~11/12，阈值 8）+ check_gates OK）；S3 ✅（`1566882` revise_output chat 专用终态（ReviseOutputArgs{target{plan_ref,output_id},instruction} + 读容忍牙 + `coerce_numbers_to_str` 顺形——探针 G 实测 provider 发裸 int 序号致 12 连拒，schema 吸收方言后 12/12）+ R20 路由器消费（最新 confirmed_scope 快照 + 活图节点）+ R19 消费侧纯核 `assemble_craft_revision`/`compose_revised_program`（prompt 消费族门控：四写手 + legacy select_clips；cut/translate/dub 确定族诚实降级）+ `_edit_graph` 机械全件抽座 `_run_wiring_proposal`（savepoint/classifier/continuation 自治/expansion 回滚转迷你包原样，revise_output 骑同座；部分覆盖带 code-composed 披露行，reminder-tail 先例）+ `_pending_plan_lines` 增 plans 阅读层（revise_plan 的 plan_id 在 chat 路的唯一来源，A-1）+ activity.py draft 桶注册；纯 pytest 571 绿（+14 新件）+ prompt_gate 七探针全绿（新探针 F = 决策包修订序位→id 精确命中 9~10/12、G = craft 修订 11/12 复跑带，阈值 8）+ check_gates OK；review 注记④销记：`resolve_source_span_texts(asset_id=None)` 回退**原样保留**——本路径指认恒钉 id（快照/@output），不碰该回退）；S4 ✅（`4dab35c`写门 `revise_selects` 分支（member_index 编辑 + 同集合 bounds 重校验 + verdict/reason 强制重述 R3 + idem 保留 + state→revised select 首个 revised 写者 + 一调用一 journey + settled 闭态 + replay 零写）+ 纯判别座 `select_revision_phase`（riding plans 状态谱 → pre_dock/docked/post_run）+ `read_journey_plan_rows` 全状态读座 + 终态工具双注册（plan path + chat path，terminal，pending_disposition 双路扩座随 RevisePlanArgs 同律）+ 迷你编译座 `compile_plan_rows_package`（只含变化子集，map 键 = 真实行 id）+ 三金钱态接线（dock 前零仪式 = 纯门修订 + 一句确认叙事（空 prose 落 code-composed 事实行，reminder-tail 先例）；dock 后未确认 = `_redock_journey_package` 抽座复用（plan/chat 两路 `_revise_plan` 尾段机械抽座——顺手修复 iter-2 ⑦ 潜伏崩溃：caption_mode 在 spec JSONB dict 上属性访问，改 `.get()`）；run 后 = riding compiled plans supersede-继任（spec 原样携带——换选换的是 SOURCE 不是 deliverables）→ 存活 riding 行迷你编译 → 同座重确认）+ 双 prompt 增 revise_selects 判定条/SPEECH 职/反形路由 + 纯测试 +14 件（585 绿；test_exploration_tools_pure 注册表面漂 gate 更新为五动词）+ S-explore-4 确定性尾剧本座 `scratch/s_explore_4_deterministic_drive.py`（**未跑验证**——需活 API/worker 配额；LLM 拍位随 S9 常驻座）；prompt_gate 全量复跑按用户指示跳过（2026-09-23：用户要求只做代码层检查，门禁与 live 回归由用户自跑））；S5 ✅（`4034785`——兑现审计纯核 `app/pipeline/run_review.py`（N-58 分词：verify 住执行图、review 住 chat 边缘触发回合）：输入 = confirmed_scope 快照 + landed outputs（baked render_spec 读轨）+ ledger captures → 兑现事实清单（产出类型/语言齐否 + clip 时长 vs 裁切区间 + 字幕轨/翻译轨/配音存在性 + outputs.quality verify 旗 + 实扣 vs 报价区间 + charge_over_quote 缺口键）；零 LLM 零 DB；gaps 保守（只点名数据证明缺失的）+ legacy 无快照读容忍（承诺面空 = 零 gap）；`review_fact_lines` 有界渲染（landed 12 / promised 8 / gaps 6 结构帽）+ 触发回合注入（`_run_review_lines`：workflow_steps.output_refs → outputs、ref.run_id capture 求和、注入 run_completed 事件行；读失败降级空块 = pre-S5 姿态原样）+ `trigger_system.j2` run_completed 分支改写（事实先述逐条 / 主观质量措辞零字枚举（never 'great'/'polished'/'惊艳'/'效果不错'）/ needs_human 平述不软化 / GAP 一句诚实 + 建议出口 = 既有编号选项问机制零新 UI / 无事实块 = legacy 回退既有 reads）+ JUDGMENT 段拍 5 carve（事实对比本身是画布看不见的value）+ 纯测试 18 件（603 绿）+ S-explore-5 确定性尾剧本座 `scratch/s_explore_5_deterministic_drive.py`（**未跑验证**——需活 API/DB；LLM 收官拍位随 S9 常驻座）；自治修不做（P2）；prompt_gate 复跑按用户指示跳过（同 S4 注记））；S6 ✅（`7f5e2c2`——Memory 三窄切：① `get_artifact` perception read（ADR-088 §7 洞销账：tenant 法诚实 miss / 候选集成员有界渲染 cap 12 / pick R7 解引用（指向段落随读）/ 计划卡 deliverables+open gaps / unknown-kind 回退）+ 注册（非 checkpoint-eligible，get_node 同律 edit-prep）+ 并入 PLAN/CHAT 双路 reads（revise_selects 双路在册故其 edit-prep read 双路随行）+ i18n `chat.inspecting.artifact`/`inspectingDone.artifact` en→zh；② Historical Journey Reuse：context.py 「Past journeys」有界块 cap 3 新先（`read_journey_summaries` + `journey_summary_line` 一措辞两座 + None-safe 排序牙——stub 会话不触发列默认）；③ Exemplar Parameter Inheritance（E5）：`output_fact`/`JourneySummary` 纯座 + 双路 `_selects_text` 注入「Last time (reference only…)」事实行——**座位微调注记**：注入落 propose_selects 观察面（计划构成前最后一帧；propose_plans 是终态工具无观察面），E5 意图原样（事实行呈现 / reference-only 永不代码覆写 / 无上一次 = 零注入）；prompt 面 = revise_selects 双 bullet 增 get_artifact read-first 指针（注册表扰动从简）；R25 按 E6 砍 = 零代码；纯测试 +22 件（625 绿；test_perception_pure/test_trigger_turn_pure 注册表面漂 gate 按设计更新为新成员）+ web tsc 绿；prompt_gate 复跑按用户指示跳过（同 S4/S5 注记））；S7 ✅（`228a1d1`——过程可见升级：wire additive `at`（全帧出生戳，ISO UTC）+ `duration_ms`（真活跃 span 的 settle 帧才有；born-completed 里程碑 = 瞬时事实不带假零；monotonic 计时——墙钟调整永不造负值）+ web 镜像类型（`at?`/`duration_ms?`）+ reducer upsert 保留首见 `at`（settle 帧的 at 是闭合时刻，行永不移动）+ NAMING = N-58 ⑥ 已在 S0 词表先行登记，本切纯落地；`lib/chatTimeline.ts` 共享时刻排序层（`momentOf`/`orderMoments`/`buildConversationUnits`——runStreamUnits 排序律推广到非 run 期，纯无 React）+ ChatDock 双路入流（run 路 activity 单元入 timed 走同一 (t,order) 律、钉底 chrome 律不动；非 run 路 conversationUnits 单流穿插）+ ActivityStream 固定底块退役（组件收窄为 `ActivityRow` 单座）+ ActivityRow 耗时耳语（右置 text-xs tabular-nums，`formatElapsed` 唯一措辞复用零新键）+ 有界展开（count 载荷才展开 = E7 诚实边界「无载荷的行不假装可展开」；展开内容 = 全文案行 + 计数 + 耗时——候选内容详情住画布卡面不复制）+ i18n `chat.activityMeta.count` en→zh；thinking 让位逻辑 / checkpoint 气泡 / dock 三态零改动；vitest 70 绿（chatTimeline 排序/穿插/undated/tie 7 件新 + reducer at 保留 2 件新）+ web tsc 绿 + api 纯 625 绿（T11/SSE 白名单 gate 按设计扩两键）；live 回归按用户指示跳过（同 S4/S5/S6 注记））；S8 ✅留档（`bcb4c2a`——迁移弧执行：旅程三承接面对账表入简报 §4 S8 施工记录（七话术族逐族对座——残座「节点级重写」复核为空集：prompt 消费族节点重写 = revise_output 覆盖、结构手术 = 能力完备手势缺席既有拍板）+ grep 足迹核实为机械削除清单（turn_tools 条目 / propose_turn `_edit_graph` 分支+方法（`_run_wiring_proposal` 抽座留存——revise_output 骑同座）/ chat_intent_system.j2 六处 / activity.py `_DRAFT_TOOLS` / perception get_node 措辞 / intent·service·tool_loop·schemas·scope_classifier 提及逐点复核）+ ADR-089 §8 迁移弧进度现在时注记（修订动词族落地带 commit 锚）；**裁决 = 不达标留档零删**——退役证明剧本腿（全量剧本绿）按用户指示本批未跑（未跑验证，用户自跑），edit_graph 保留注册，退役执行 = 剧本绿后按施工单一个小提交）；S9 ✅代码面（SHA 见本提交——check_gates OK + 纯 pytest 625 绿 + web tsc/vitest 70 绿复跑确认；S-explore-3 确定性尾座补齐 `scratch/s_explore_3_deterministic_drive.py`（拍 6 修订回路：R20 plan_ref 双通道/@output 单通道/legacy+越界诚实降级 + R19 装配（混合集 edit_prompt+run+uncovered 披露 / 全确定族 None 降级）+ 写门实线（edit_prompt 落盘条款可见 / 未知节点 WiringRejected；run op 故意不点火——常驻 worker 抢跑律）；六拍 live 走查脚本交付 `scratch/iter3-six-beat-walkthrough.md`（门禁先行 + 逐拍操作/预期 + reds 清单 + 验收后一步）；docs 收口 = PROGRESS §0.2 行 + JOURNEYS 拍 4/8/9/10 状态翻新——**简报归档与 edit_graph 退役故意留待用户验收后**（§6 验收口径 9：live 走查证据齐才算成，批次完成度不顶替）；prompt_gate 全量 / 三座 LLM 拍位 / 受影响旧座回归 = **未跑验证**（2026-09-23 用户拍板本批只做代码层检查，用户自跑））。交接细节 = `scratch/iter3-s2-handoff.md`。
> 母合同 = 本文 §2 Product Contract v1（P0 Product Gate 产出）+ ADR-088（§3 双状态机 / §8 Reviewer 合同 / §10 项目记忆）+ ADR-089（§4 快照 / §5 停顿定律 / §6 修订分类 / §8 迁移弧）+ JOURNEYS 旅程四拍 3/4/5/6/8/9/10 + PROGRESS §0.1 验收口径。承重既有批：迭代一（`archive/tasks-done/agent-working-loop-iter-1.md`：探索三族 + 写门 + 证据 reads + 画布卡面）+ 迭代二（`tasks/agent-working-loop-iter-2.md`：编译器 + 决策包 + Confirmed Scope Snapshot + R6 路由 + 活动键 + revise_plan，实测全绿）。

## 1. 主线与冻结条（Product Gate 拍板原文，施工硬约束）

**主线**：把 Agent Working Loop 从一次性生成闭合为**持续工作闭环**——每一次用户意图变化都落在正确的产品语义层，永不掉回 runtime 词汇。六拍总表（直接开干 / 过程可见 / 中途插话免费秒改 / 只在渲染前停一次 / 收官自检汇报 / 一句话修订零仪式）是验收母合同（PROGRESS §0.1），一切切片必须指回某一拍。

**六拍产品语义总表**（P0 Product Gate 拍板，2026-09-23——逐拍即验收定义）：

| 拍 | 用户动作 | Agent 行为 | 用户看到 | 决策/付费 |
|---|---|---|---|---|
| 1 直接开干 | 一句模糊目标（+素材） | 产品语言复述 → 立即开工看素材/检索 | 素材理解节点 +「我先看看素材」 | 无 / 无 |
| 2 过程可见 | 等待旁观 | 检索→评估→精选→结构化，连续工作不停 | 候选合集卡→精选卡→方案卡；散文 × 证据行**时刻穿插** | 无（可插话）/ 无 |
| 3 中途插话免费秒改 | 「第 2 个换第 5 个」 | 立即改选择 → 方案自动跟随；包已呈现则原地更新+新价 | 更新的卡 / 刷新的决策包 | **无新增停** / 无 |
| 4 只在渲染前停一次 | 读决策包 →「可以」 | 编译 → 报价 → 完整决策包（方案层+证据层+费用语义） | 决策包 dock | **是（本付费范围授权边界）** / 是 |
| 5 收官自检汇报 | 等结果读汇报 | **对照已批准方案逐项兑现审计**（只讲系统能确定知道的事实） | 产物 + 兑现清单叙事 + 建议 pills | 可选 / 无 |
| 6 一句话修订零仪式 | 「plan 2 的字幕太长了」/「改德语」 | 指认解析 → 语义层路由 → 金钱边界：**信封内零仪式；新付费范围 = 迷你包重确认** | 更新的产物 / 迷你决策包 | 仅当新钱移动 / 条件 |

**同一句话的三个金钱态**（拍 3/6 接缝）：「第 2 个换第 5 个」dock 前 = 免费秒改；dock 后未确认 = 决策包原地更新（停仍只有一个）；run 后 = 重做即花钱 → 迷你包重确认——零仪式在付费后**故意失效**。

**冻结条（Product Contract C，逐条即施工禁令）**：
1. **停顿定律合同语言**：每一次付费范围形成前只在该范围的授权边界停一次；已批准范围内 continuation 零仪式；只有 Scope Expansion 重新确认。
2. **决策包可编辑律**：未确认的 Decision Package = 可持续编辑的决策对象——dock 前/未确认的换选与纠正 = 原地更新 + 重编译受影响范围 + 更新 quote/费用语义 + **同一个确认动作完成授权**；「确认失效 → 再弹一次确认」实现形态明令禁止。
3. **Reviewer 边界**：确定性兑现审计 + 建议 = 主线全部；主观质量零字；自治修 = Optional/P2 不进主线；reviewer 永不自封 continuation。
4. **Memory 三不**：Project Working Context / Historical Journey Reuse / Exemplar Parameter Inheritance 三需求不合并；不新增 memory/goal 类 domain object；agent 无静默升格写口。
5. **语义层纪律**：修订三族（plan / output / select）= 产品语义层；用户永不接触 wiring/Task DAG 词汇；自由散文指令的结构闸 = R19（语言自由、范围裁决确定）。
6. **select_clips 零代码**：本批只落产品裁决文书。
7. **迭代二 §5 避让清单全量继承**：执行世界零改动（apply_wiring_ops / create_run / classifier 本体 / Start 四合取 / hold→capture→release / fencing / workflow_steps）/ 确认教义 / dock pill 唯一座 / G-1 / trigger turn 白名单 / 打字机律（新散文字段带读容忍 + 零 delta 路径 paceSettledProse）/ Activity 十规则 / R18 同框纪律 / reasoning 永不持久化 / 词表先登记 / i18n en 先 zh 镜像 / 展示文案二源律 / 凭据纪律 / worktree 纪律。
8. **验收口径**：六拍体感剧本全跑顺才算成；批次完成度不是验收。

## 2. Product Contract v1（P0 拍板，施工项按闭环边排序）

1. **闭环脊柱**：chat path 产品语义化（修订三族 + 探索族 + reads 注册进 run 后对话面 + 发现型判定段 parity + loop 预算复审）。服务拍 6/10。
2. **方案身份与修订路由（R20）**：快照增 plan→nodes 显式映射 + 读面纯函数 + plan 行 `compiled` 态写者（连带 `read_journey_plans` 状态过滤 = iter-2 review 注记①同批必办）。服务拍 6 与拍 3 dock 后态。
3. **一句话修订双动词**：revise_output（craft/how：指认 + 用户的话 → 语义层路由 → 信封内零仪式 / 信封外迷你决策包重确认）+ revise_plan post-run 可达。语义层不全 = 诚实降级，永不静默。服务拍 6。
4. **选择修订三金钱态**：dock 前零仪式 / dock 后决策包原地更新重报价 / run 后 expansion 迷你包重确认（含 plan 重指 select 的 P/A Gap 开合）。服务拍 3/6。
5. **收官兑现审计**：确定性兑现清单（许诺 vs 落地 + `outputs.quality` 证据 + 存在性探针）注入既有触发回合；主观质量零字；scope 外 = 建议唯一出口。自治修 = Optional/P2 不进主线。服务拍 5。
6. **过程可见升级**：散文 × 证据行时刻穿插（非 run 期与 run 期同一排序律）+ 耗时 + 有界展开；wire 白名单 additive 扩时间戳键；不持久化。服务拍 2。
7. **Memory 三需求窄切**：Project Working Context（get_artifact 按需读 + journey 维度）+ Historical Journey Reuse（有界摘要行入 context）+ Exemplar Parameter Inheritance（上次方案规格 → 新方案默认事实行，复用摘要行作事实源）。服务拍 10。**待小拍板**：R25 窄门留/砍（§3-E6）。
8. **迁移弧裁决与证明**：select_clips 产品裁决落档（执行世界永不做发现；退役随旧路；本批零代码）；edit_graph 在项 1/3/4 落地后跑退役证明（剧本全绿 + 旅程三承接面对账）→ 达标即退役，不达标留档阻塞证据；propose_tasks + 零探索退化形态挂账 PROGRESS 池（词汇卫生动机，非产品动机）。
9. **六拍终态验收**：三座常驻剧本（换选 / 修订回路 / reviewer）+ 逐拍 live 走查证据；六拍全顺才算成。

**明确不做**：零探索退化形态 / propose_tasks 退役（挂 PROGRESS 池）；R25 宽面（定位大迭代）；深度看片复核（池）；自治修（P2）；select_clips 任何代码改动。

## 3. 工程拍板项（全带推荐答案）

**E1. plan→task 显式映射形态**：`compile_plans` 是公开纯函数且有 iter-2 调用方/测试——推荐**新增返回对象** `CompiledScope{tasks, plan_task_map}`（`plan_task_map: {plan_id: [task 序号区间]}`），`compile_plans` 保留为薄包装返回 `.tasks`（旧调用零 diff）。映射随编译一次产出，杜绝事后位置推导漂移。

**E2. 快照扩字段**：`confirmed_scope` 增 `plan_task_map` 键（additive，legacy 快照无此键 = 读容忍 → 修订路由器诚实降级指回 @output 通道）。推荐。键名随 NAMING 登记。

**E3. plan 行 `compiled`/`superseded` 写者（双态首写）**：Start 落戳成功后在**同一事务**把本包 plans 行 state → `compiled`（探索写门增 `mark_compiled` 分支）；post-run plan 级修订 = 旧行 → `superseded` + **继任行**（新 id、同 journey、revised spec——`revision_of` 指针不建，N-57 无版本树律不变；`compiled → superseded` 是状态机词表内路径）。**连带**：`read_journey_plans` 增状态过滤（只回 {ready, revised}——review 注记①）；`compile_plans` 对 compiled/superseded 的硬拒不变（读面过滤后不可达）。

**E4. revise_output 座位与 args**：终态工具，**chat path 专用**（craft 修订的对象是已产出/已编译的东西，pre-run 无对象——pre-run 的 craft 诉求归 revise_plan outputs 重述）。args = `{target: {plan_ref?: string（序位词如 "2" 或 plan_id）, output_id?: UUID}, instruction: str}`——指认二选一，全空 = ask 反问；读容忍牙（null → 缺省）。执行 = R20 路由器解节点集 → 只对 **prompt 消费族**节点组装 `edit_prompt + run`（确定族节点如 cut_segments 无 prompt 语义 = 诚实降级散文，说明能改什么不能改什么）→ savepoint 过 `apply_wiring_ops` → `classify_graph_scope` 消费裁决 → continuation 落盘自治跑（零仪式）/ expansion·unproven 回滚转迷你决策包 dock（只含变化子图 + 价差）。机械全件复用 `_edit_graph` 先例；classifier 本体零改动。

**E5. Exemplar 继承机制 = 事实行注入，不做代码侧参数映射**（推荐）：ADR-078「参数由代码从骨架映射」约束的是执行 spec；方案字段本身是产品语义层，LLM 读事实提方案是合法形态。落地 = 历史旅程摘要行携带上次方案规格（语言/字幕/画幅/配音计数），新 journey 的 propose_plans 观察面在检出 exemplar 意图时把它作为默认事实行呈现；无上一次 = 零注入。不做代码强制覆写（那会造「agent 提了用户没要的参数」的幽灵）。

**E6. R25 偏好升格窄门：留 or 砍**（用户待小拍板项）。推荐：**砍出本批**——低频、sink 触及 persona 治理（定位大批次的辖区），闭环六拍不依赖它；反专断的结构性保证（无静默写口）天然成立。留的代价 = 提议面 + 授权写口 + persona PUT 接线 + 剧本座，约一片体量。若拍「留」，切片排到末位（S6.5）。

**E7. 活动帧扩键与「可展开」的诚实边界**：wire additive 扩 `at`（帧出生戳，全帧）+ `duration_ms`（completed 帧）两键——**不扩 summary/详情载荷**：里程碑行的展开内容 = 既有白名单字段（计数 + 文案行 + 耗时），候选内容详情住画布卡面（R1/R3 已有座位，活动行不复制卡面）。「证据行可展开」的兑现 = 耗时可见 + 有载荷时展开，无载荷的行不假装可展开。推荐。

**E8. chat path loop 预算**：`chat_intent_agent` max_iterations 6 → **12**（对齐 plan path 的 iter-2 实测教训：探索链一回合多动词 + 拒收回声都吃预算；`max_iterations` 是预算不是阈值）。prompt_gate 全量复跑护航。

**E9. 新剧本座编号**：`S-explore-3`（拍 6 修订回路：craft continuation 零仪式 + plan expansion 重确认 + run 后换选）/ `S-explore-4`（拍 3 插话换选：dock 前零仪式 + dock 后原地更新同确认座）/ `S-explore-5`（拍 5 reviewer：兑现事实入散文 + 建议出口 + 主观零字断言）。reviewer 不单独立族——探索主链剧本的延续座。fixture 纪律照旧（scenario/ 前缀、真实 words、禁共享 demo key）。三座的确定性尾先行（S23 先例：deterministic drive 对活 API），LLM 拍位串行复跑。

**E10. 新词登记（NAMING 先行，N-58 判例行 + §2 词表行）**：`revise_output`（craft 修订动词）/ `revise_selects`（选择修订动词）/ `run_review`（兑现审计纯核模块，`app/pipeline/run_review.py`——与图内质检 `verify` 分词注记：verify 住执行图，review 住 chat 边缘触发回合）/ `get_artifact`（ADR-088 §7 点名 read 洞销账）/ 快照键 `plan_task_map` / 活动帧键 `at`+`duration_ms` / exploration 双态写者语义（`mark_compiled` / supersede-继任）。登记后再进代码。

## 4. 施工切片（依赖序；每片独立 commit 级自绿）

**S0 裁决与词表（docs-only）**：NAMING N-58 登记（E10）+ select_clips 产品裁决落档（ADR-089 §8 PENDING 销记——执行世界永不做发现，退役随旧路；调用面清单仅作迁移机械证据入档）+ PROGRESS 需求池增「零探索退化形态（propose_tasks 退役前置）」挂账行。

**S1 R20 方案身份与修订路由**（项 2；纯后端零 prompt 面）：
- `scope_compile`：CompiledScope 返回对象（E1）+ `build_confirmed_scope` 增 `plan_task_map`（E2）；
- 探索写门：`mark_compiled` 分支 + supersede-继任路径（E3）+ `read_journey_plans` 状态过滤；
- Start 落点接线（service.py 既有快照写口同事务）；
- 修订路由器纯函数：指认（序位 / plan_id / @output 反查）→ 快照映射 → task 切片 → fill_key → 节点集；legacy/歧义 = 诚实降级；
- 纯测试：映射完整性 / 过滤 / 路由器全谱（含 legacy 拒绝）。

**S2 闭环脊柱：chat path 产品语义化**（项 1；prompt 面）：
- `chat_intent_agent` 工具集增 `exploration_chat_tools()` 投影 + reads（get_artifact 在 S6 到齐后并入）；
- chat 相位 prompt 增发现型判定段（R6 parity：post-run「再挑两条」= 新 journey 探索链；修订话术 → 修订动词；「更智能 = 事事探索」永禁照抄）；
- max_iterations 6→12（E8）；
- prompt_gate 全量复跑 + 评估 post-run 发现型探针（12 发看带再封线）。

**S3 revise_output + R19 接线**（项 3；依赖 S1+S2）：
- 终态工具 + args（E4）+ R20 路由器消费 + ops 组装（edit_prompt+run，prompt 消费族门控）+ classifier 裁决消费（_edit_graph 机械全件复用：savepoint / GraphDelta / tasks_for_graph_nodes / continuation 自治跑 / expansion·unproven 回滚转迷你 dock）；
- 迷你决策包 = 既有 `_dock_plan_as_question` 座（只含变化子图 + 价差估价）；
- 诚实降级三态：无快照/legacy → 散文 + @output 兜底反问；目标全是确定族节点 → 「能改的是…」；部分可改 → 部分执行 + 散文说明未覆盖部分；
- review 注记④再评估：本路径指认恒钉 id（快照/@output），不碰 `resolve_source_span_texts(asset_id=None)` 回退 → 原样保留并在简报销记；
- 纯测试 + prompt_gate + review 注记②探针评估（决策包上的修订，12 发看带）。

**S4 选择修订三金钱态**（项 4；依赖 S1，chat 侧依赖 S2）：
- 写门 `revise_selects` 分支：member_index 编辑 + bounds 重校验 + idem 保留（revise_plan 同律）+ state → `revised`（select 首个 revised 写者）；
- 终态工具 revise_selects（plan path + chat path 双注册）；
- dock 前：纯门修订零仪式 + 一句确认叙事；dock 后未确认：复用 _revise_plan 整包重编译 + 原地 supersede 重报价（**决策包可编辑律**：同一确认座，禁新弹确认）；run 后：select 修订 → plan supersede-继任（E3）→ 重编译 → 迷你包 → 重确认；
- 纯测试 + 剧本 S-explore-4 座（S9 全量）。

**S5 收官兑现审计**（项 5；依赖 S1 快照作比对基）：
- `app/pipeline/run_review.py` 纯核：输入 run + landed outputs + confirmed_scope → 兑现事实清单（产出类型/语言齐否、时长 vs 裁切区间、字幕轨存在性、配音存在性、`outputs.quality` 既有旗、实扣 vs 报价）；零 LLM；
- 触发回合 context 注入事实清单（有界）+ `trigger_system.j2` run_completed 分支改写（先叙述事实、主观零字、缺口出建议）；
- 建议出口 = 既有编号选项问机制（零新 UI）；
- 纯测试 + prompt_gate + 剧本 S-explore-5 座。**自治修不做（P2）**。

**S6 Memory 三需求窄切**（项 7；get_artifact 就位后并入 S2 工具集）：
- Project Working Context：`get_artifact` read（perception 注册：按 id 读探索产物/产物的 user-safe 全字段；ADR-088 §7 洞销账）；
- Historical Journey Reuse：`build_context` 增有界块——历史 journey 各一行确定性摘要（goal + 方案/产物计数 + 最近快照规格事实），cap 3 条新先；
- Exemplar Parameter Inheritance：摘要行携带上次方案规格；propose_plans 观察面默认事实行注入（E5）；
- R25 窄门按 E6 拍板执行（砍 = 零代码；留 = 末位切片）；
- 纯测试 + prompt_gate（read 注册扰动目录面）。

**S7 过程可见升级**（项 6；web 为主，wire 键先行）：
- wire：ActivityFrame additive `at` + `duration_ms`（E7）+ web 镜像类型 + NAMING 注记；
- web：抽共享时刻排序层（runStreamUnits 排序律推广到非 run 期：messages.at × activity.at 单流穿插）；ActivityStream 固定底块退役入流；ActivityRow 增耗时 + 有界展开（E7 诚实边界）；thinking 行让位逻辑、checkpoint 气泡、dock 三态全部回归不动；
- vitest（排序/归并/reducer）+ tsc；i18n en 先 zh 镜像。

**S8 迁移弧执行**（项 8；依赖 S2/S3/S4 落地）：
- edit_graph 退役证明：旅程三承接面对账表（每话术族 → 新座位）+ 全量剧本绿 + grep 零生产调用；
- 达标 → CHAT_TOOLS 除名 + dispatch 删除 + prompt 清理 + S4 剧本本质迁入 S-explore-3；不达标 → 留档阻塞证据零删；
- ADR-088/089 注记现在时改写（修订动词族落地 / select_clips 裁决 / 迁移弧进度）。

**S8 施工记录（2026-09-23，结论 = 不达标留档零删）**：

旅程三承接面对账表（每话术族 → 新座位）：

| 话术族 | 新座位 | 状态 |
|---|---|---|
| 改 docked 决策包某计划做什么（what） | `revise_plan`（plan/chat 双路） | ✅ S2/S4 |
| 换选段（pick 换同集合另一段） | `revise_selects`（三金钱态） | ✅ S4 |
| 已产出/已确认作品的 craft（wording/tone/sharpness） | `revise_output`（chat 专用终态，骑 `_run_wiring_proposal` 同座） | ✅ S3 |
| 单产物精确 clip-spec 操作（trim/caption tweak） | `edit_output`（受控四件，ADR-090；原 apply_edit_ops B1 已退役） | ✅ 既有 |
| pre-run craft 诉求 | `revise_plan` outputs 重述（E4 判词） | ✅ S2 |
| 新增不存在的产出（新语言版/新类型/加量） | `propose_tasks`（旧路保留；退役弧 = PROGRESS 池「零探索退化形态」挂账） | 保留 |
| 结构性 graph surgery（add/delete/connect/disconnect 手动布线） | **无座位 = 设计**（能力完备手势缺席——既有拍板；产物删除在画布亦无家） | 设计缺席 |
| 残座：「修订动词族表达不了的节点级重写」 | edit_graph 当前仍占此座（`chat_intent_system.j2` 反形路由条）；经上表逐族复核 = **空集**（prompt 消费族节点重写 = revise_output 覆盖；结构手术 = 设计缺席） | 空集证明待剧本腿 |

退役证明三腿状态：① 对账表 = 本表（代码层覆盖完整，残座为空集——按设计）；② 全量剧本绿 = **未跑验证**（用户指示本批只做代码层检查；全量剧本 + prompt_gate 由用户迭代完成后自跑）；③ grep 零生产调用 = 未执行删除故不满足——当前足迹（= 达标后的机械削除清单）：`turn_tools.py` CHAT_TOOLS 条目 / `propose_turn.py` `_edit_graph` 分支+方法（`_run_wiring_proposal` 抽座**留存**——revise_output 骑同座）/ `chat_intent_system.j2` 六处（判定条、wiring ops 清单、边界条、反形路由、SPEECH 职、name 条）/ `activity.py` `_DRAFT_TOOLS` 除名（revise_output 留）/ `perception` get_node 描述措辞 / `intent.py`·`service.py`·`tool_loop.py`·`schemas.py`·`scope_classifier.py` 的 WiringProposal 提及逐点复核。

**裁决：不达标（剧本腿缺）→ 按简报法留档零删**——edit_graph 本批保留注册；退役执行 = 用户全量剧本绿后的一个小提交（上表即施工单）。

**S9 六拍终态验收**（项 9；收尾）：
- 三座常驻剧本全绿（S-explore-3/4/5：确定性尾 + LLM 拍位）；
- 全量门禁：纯 pytest 全量 + check_gates + prompt_gate 四探针 + web tsc/vitest + 受影响旧剧本 live 复跑（串行，不与 gate 并发）；
- 六拍逐拍 live 走查证据（`scratch/iter3-six-beat-walkthrough.md` + 截图/日志；live 走查由用户跑，本批交付脚本与检查表）；
- docs 收口：PROGRESS §0.2 行 + JOURNEYS 拍 3/4/5/6/8/9/10 状态翻新 + 本简报归 `archive/tasks-done/`。

依赖：S1→S3/S5；S2→S3/S4(chat 侧)/S6；S1→S4；S7 独立可插入任意空档；S8 依赖 S2/S3/S4；S9 收尾。执行序：S0 → S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8 → S9。

## 5. 避让清单（冻结条全文 = §1；此处列本批高发撞击点）

- 执行世界零改动七件（apply_wiring_ops / create_run / classifier 本体 / Start 四合取 / hold→capture→release / fencing / workflow_steps）——R19 接线 = 消费裁决不是改裁判。
- 决策包可编辑律：dock 前修改**禁止**实现成「确认失效重弹」；同一确认座同一动作。
- 修订动词的读容忍牙（null→缺省）+ 零 delta 路径 paceSettledProse——打字机律两牙同批检查。
- 探索写门扩展（mark_compiled / revise_selects / supersede-继任）是本批门内施工，证据校验/幂等/savepoint 三牙原样；执行写门对 exploration 族的拒收不变。
- `compiled`/`superseded` 首写者落地 = `read_journey_plans` 状态过滤同批（缺一天 = 整包重编译炸）。
- reviewer/revise 散文永不发明主观质量判断；建议 pill 文案 user-safe。
- 活动帧扩键仅限 `at`/`duration_ms`；params/raw results/reasoning 永不上 wire。
- Memory 三不：不合并、不开新 domain object、无静默升格写口。
- 迁移弧纪律：edit_graph 退役必须先证明后执行；propose_tasks 零改动；select_clips 零代码。
- Phase 2 步⑤（相位面收窄）仍 HOLD——S7 只在现有 ActivityStream/units 座位施工。
- 新词先登记 NAMING（E10 清单）再进代码；i18n en 先 zh 镜像；展示文案二源律（命名 = LLM 提案 / 事实 = 世界自证；冻参模板永禁）。
- 凭据纪律；worktree 纪律（git stash 用唯一 tag 记 SHA）。

## 6. 验证纪律

- 每 commit 自绿：compileall + 相关纯 pytest（新纯核全谱：编译映射 / 路由器 / 写门新分支 / run_review / context 摘要块）。
- prompt 面改动必跑 prompt_gate（S2/S3/S5/S6 都是 prompt 面）；失败 = 复跑一次再二分，永不调阈值；新探针先跑 12 发看带再封线。
- 批级收口：纯 pytest 全量 + check_gates + web tsc/vitest + 受影响剧本 live 复跑（串行）。
- 剧本：S-explore-3/4/5 三座常驻（E9）；旧座回归（S-explore-2 / S23 / S4 / S7 / S13 / S16 / S19 / S22 受影响面）。
- 认知验收三问（PROGRESS §0.4 规则 9）：agent 看见什么（快照读面 + 决策包三层 + 兑现事实清单）/ 表示一致吗（plan↔tasks↔quote 同源编译；修订走同一编译器）/ 怎么知道对了（classifier 裁决 + 兑现审计事实 + 剧本断言）。
- live 验证硬前提：dev API + worker + MiniMax 配额；worktree 与主 checkout 共享 dev DB——跑 live 前停旧栈防 worker 抢队列。没跑过的项在报告与文档如实标「未跑验证」。

## 7. 验收标准

1. **拍 3**：dock 前换选零仪式（精选卡更新、方案跟随、无停顿）；dock 后换选原地更新同确认座（禁新弹确认的断言入剧本）。
2. **拍 5**：run 完成 → 收官散文含兑现事实（类型/语言/时长/字幕/配音逐条）+ 缺口建议 pill；主观质量措辞零字（剧本断言）。
3. **拍 6**：craft 修订 continuation 零仪式自治重跑；plan 级 expansion 迷你包（只含变化 + 价差）重确认；「plan 2」序位指认精确命中（不错对象）。
4. **拍 2**：非 run 期散文 × 活动行时刻穿插单流呈现；耗时可见；run 期回归不破。
5. **拍 10**：「再挑两条」post-run 开新 journey 探索链；「照上次的样子」新方案默认带上次规格事实行；历史旅程摘要有界入 context。
6. **R20**：快照含 plan_task_map；compiled/superseded 写者与读面过滤闭环；legacy run 诚实降级。
7. **迁移弧**：select_clips 裁决落档零代码；edit_graph 退役证明达标即退役（不达标留档）；propose_tasks 挂账入池。
8. **零改动实证**：执行世界七件行为面 diff 为零；打字机律/Activity 十规则/R18 同框回归绿。
9. **六拍全顺**：live 走查逐拍证据齐（用户跑）——批次完成度不顶替本条。

## 8. 收口

- PROGRESS §0.2 本批行；JOURNEYS 拍 3/4/5/6/8/9/10 状态翻新 + 横切 6 销记；NAMING N-58；MODULE_ARCH §7 登记 run_review / 修订路由器座位；ADR-088/089 注记现在时；verification-contracts.md 三座新剧本注册。
- conventional commits 每 commit 自绿；报告 = 改动文件 / 测试 / 剩余风险 + 迁移弧进度复述；本简报随收口归 `archive/tasks-done/`。
