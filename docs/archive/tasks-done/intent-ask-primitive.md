# intent-ask-primitive 实施简报——提问机器 + 任务书 slot 化 + 停靠确认 + 方向检查点

> Status: ✅ 期 1/2/3/4 全部落地（期 4 2026-07-30：Suspend/waiting + 方向检查点 + autonomy 生效 + bail 级联；**期 4 补四 2026-07-30：意图覆盖缺口清扫 G-1/G-4/G-2 + G-5/G-6 收编**）
> 依据：CHAT_ARCH §3（IntentProposal 二态，N-14）/§8（pending_intent 持久化与恢复）；NAMING §5（新词族登记 + 翻案判例）；AGENT_ARCH §12.3；`docs/research/opusclip.md` §9（Agent Opus HITL 实证）；Mastra suspend-resume / HITL / agent-approval 官方文档（机制语义参照，非依赖候选）
> 前置：output-quality-verify 期 1 已落地——其 `quotes_count`/`carousel_count` 扁平字段是**过渡形态**，本简报期 2 由 `IntentSlot.count` 取代（全库退役，不留过桥层，宪法 §1）；与 quality 期 2/3 并行无依赖，唯 checkpoint 的 orchestrator 改动与 verify 期 3 同文件，review 时对账
> 迁移：1 个 alembic 迁移（`messages.question` / `messages.answer` 两个 JSONB nullable 列），down_revision 跟落地时最新 head。**slot 化零表迁移**——全部住在 JSON 载荷层（pending_intent / run.context / 请求体）

## 期 4 落地实录（2026-07-30）

- **`Suspend` 异常 + 捕获分支**（`orchestrator.py`）：checkpoint runner 派生选项 → 自有会话落 question 并提交 → raise Suspend(options)；execute_step 捕获后节点转 `waiting`（`spec.suspend_payload` 存选项 + question_message_id）、run 转 `WAITING_HUMAN`，不做级联。重入是队列式的：答案写入 `spec.answer`、节点回 pending、run 回 RUNNING → worker 重认领从 runner 顶上重跑，answer 分支直达 done（summary = 选定方向）。
- **`run_checkpoint` 瘦节点**（`node_runners.py`，注册进 STEP_RUNNERS 不进 SKILL_REGISTRY，禁 #6）：零 LLM（禁 #4，e2e 实测节点 cost 为 NULL）——选项代码派生自 `understanding.key_arguments` ≤3 个"聚焦：{论点}" + "全场高光"默认项，字母 id（a-d），allow_freeform；label/问句语言跟素材语言（`_source_language`，en/zh 两档其余回落英文）。`spec.for=direction` 住用途（N-19）。
- **compile_graph autonomy 裁决**：review 档 full run 在 understand(3) 与 plan(5) 间插 checkpoint(seq 4, inputs=[persona, understand]——persona 排序约束传递保留）；auto 档不插（禁 #12）、targeted 不插、mode② 不插（compile_graph 单测级验证四拓扑）。
- **answer 分派 checkpoint 分支**（`answer_question`）：识别 = choice + `workflow_run_id`（dispatch 标记）；option/freeform → `resume_waiting_checkpoint`（spec.answer + 节点 pending + run RUNNING）；bail → `bail_waiting_checkpoint`（done + spec.bailed + summary "Bailed by user"）→ `_cascade_skip(reason="user bailed")` 非失败变体 → 提交后 `maybe_finalize_run` 收官 COMPLETED——永不 failed（禁 #5），"注明用户中止"落节点 summary 进 run 聚合摘要（不动 COMPLETED 行 error 恒 NULL 的既有契约）。
- **autoResume 同分派**（`chat()`）：typed 答案命中/自由文本回合掉 checkpoint 问题时同样唤醒 run；**不过 `_propose_turn`**——唤醒即续聊（步骤流可见续跑），回确定性行 "Direction locked: {label}. Resuming the run."，避免对 "a" 发起 LLM turn。
- **finalize 两处谓词补 waiting**：`maybe_finalize_run` active 谓词 + `finalize_stuck_runs` SQL；`reap_stale` 只动 running 天然不碰 waiting。
- **director_plan 消费 answer**：`_checkpoint_direction` 按 kind 读上游 checkpoint spec——option → `task_book.direction={argument_ids, text}`（默认项 argument_id 空 → 缺省不加键 = 现状行为）；freeform → `{text}` 原文。j2 加 Direction 段（显式 slot focus 优先的措辞）；优先级 slot.focus > checkpoint > director——explicit 字段仍由 `_align_storyboard_slots` 代码强制，方向只是 prompt 层引导。`_load_understanding` 改按 kind BFS 穿透 checkpoint 一跳。
- **前端**：StepMarker/RunCard 加 waiting 行（CircleHelp 图标，步骤数据结构不动，禁 #14）；GenerationOverlay 加 mid-run dock 复活（SSE 流里出现 waiting checkpoint → 重取待决问题上 dock）；dock/占位符/autoResume 全复用期 3 choice 形态零改动；i18n `stepKinds.checkpoint` en/zh。`useRunEvents`/SSE 无需改（waiting_human 非终态已成立，流保持开着推 step.updated）。
- **e2e 实录**（真实 LLM + 真实队列，验收条目 6-9）：条目 6 ✅（review full 含 checkpoint；auto full/targeted/mode② 不含）；条目 7 ✅（option "a" → storyboard 槽 argument_ids 含优先论点 a1；typed freeform → spec.answer 原文 + run completed；bail → 下游全 skipped "user bailed"、run COMPLETED；补测默认项 "d" → 无 direction 注入、storyboard 广覆盖 a1-a6 现状行为）；条目 8 ✅（waiting 中跑 `finalize_stuck_runs` 不收官，答案到后续跑完成）；条目 9 ✅（checkpoint 节点 cost NULL）。Post-only 槽三次 run 全绿；scratch 项目/用户已清理（messages 回到 73 基线）。
- **偏离简报处**：seq 用整数 4/5（简报 "3.5" 是示意，seq 列 Integer）；checkpoint typed autoResume 不走 `_propose_turn`（简报只说 answer 端点分派，chat 路径同语义取确定性 ack）；选项/问句文案语言跟素材语言而非 UI 语言（服务端够不着 i18n cookie）；"注明用户中止"落节点 summary 而非 run.error；choice dock 仍无 bail 按钮（复用期 3 形态，checkpoint bail 本期走 API/契约层，UI 入口归后续）。
- **运维**：改 pipeline 代码后已重启常驻 worker 验收（旧码 worker 遇 checkpoint 节点会 STEP_RUNNERS KeyError 标 failed）；orchestrator.py 与 quality 期 3 同文件，review 时对账。

### 期 4 补：checkpoint 过期 + bail UI + 纯函数测试 + 多 run 级联（2026-07-30 追落）

- **过期语义**：超时 = **自动以默认项回答并续跑**（review 档超时降级为 auto 档行为），不是 auto-bail——兑现 §2.7 兜底文案"离开不中断，我会按最佳判断完成"；弃做交付零产物违背该承诺。默认项无 argument_id → director_plan 零注入 = 现状行为。
- **过期机制**：`expire_stale_checkpoints`（orchestrator，worker `_tick` 每拍调用，静默零成本）扫 `waiting` 且 `started_at` 过 TTL（`settings.checkpoint_expiry_seconds`，默认 1800s）的 checkpoint → 守护式 `UPDATE messages SET answer … WHERE answer IS NULL`（用户答案与扫描竞态永远赢）写 `{kind: option, option_id: 默认项, text: "expired"}` → `resume_waiting_checkpoint` 唤醒。机器标记 `"expired"` 复用期 1 `superseded` 同款模式。
- **bail UI 入口**：QuestionDock choice 形态加可选 `onBail`——**仅 checkpoint 语境**（dock 的问题带 `workflow_run_id`）渲染"放弃生成"ghost 按钮；chat 选项卡不给（下一句话天然 supersede）。overlay `handleCheckpointBail` 复用 answer `kind=bail`（端点内同步完成级联+收官）→ QA 入档 + info toast + 关 overlay。QA 入档文案按 `bail + workflow_run_id` 分流：checkpoint bail → "已停止生成"，task_book bail → "已取消——回到草稿"（`qaAnswerText` 加 hasRun 参）。
- **纯函数测试**：`tests/test_intent_layer_pure.py`（28 例，`uv run --extra dev python -m pytest`，零 DB 零 LLM——范围纪律写进文件头，防止重蹈旧套件漂移）：compile_graph 全拓扑（auto/review/targeted/mode②/hook/render/per-slot 扇出）、`ordered_slots`、`slot_step_label`、`derive_context_fields`、`_match_option`、`merge_explicit_slots`、`_align_storyboard_slots`、`_checkpoint_direction`（stub db）。
- **多 run 并停级联**：`_settle_open_questions` 返回 bailed run ids——supersede 命中带 `workflow_run_id` 的 checkpoint 问题时同笔级联 `bail_waiting_checkpoint`；`_dock_question` 换 `(message, ids)` 签名，各调用点（chat / answer_question / sync_task_book_question / dock_checkpoint_question）提交后统一 `finalize_bailed_runs` 收官 COMPLETED。单待决不变量从此不会搁浅 run。
- **顺手修正**：`run_checkpoint` 重入 summary 的 label 解析改 suspend_payload 选项优先（`answer.text` 可能是机器标记 `"expired"`）；`older_than or 默认` 的 falsy 坑（timedelta(0) 被吞）改 `is not None`。
- **前端过期配套**：`qaAnswerText` expired 形态（muted）；overlay 陈旧 dock 清理 effect（本 run checkpoint 离开 waiting → 重取待决，空则清 dock）；ChatModal 陈旧 dock 靠重开/409 兜底（次表面）。
- **e2e 实录**：过期——TTL 内不扫（expired=0）✅、TTL 过 → 默认项+expired 标记+completed ✅、summary 显示默认 label ✅、零方向注入 ✅；多 run——run A 并停中被 run B 的 dock supersede → 级联 bail + COMPLETED + 下游 skipped("user bailed") ✅、run B 不受影响正常唤醒完成 ✅。
- **运维坑（实录）**：本机曾同时存活**两个 worker**（14:41 历史进程 + 15:31 新启）——kill 按单个 PID 没杀全，旧码 worker 抢到 run B 的 checkpoint 执行（supersede 发生但无级联 bail），排查先 `ps aux | grep app.worker` 确认唯一存活。教训：重启 worker 要全杀再启，uv run 是 wrapper+child 两个进程。
- **已知边界（修复后剩余）**：修复前遗留的搁浅 run（问题已答、节点仍 waiting）不会被过期扫描复活（守护 UPDATE 跳过已答行）——本迭代前的 dev 遗留需手工清理，线上无此存量。bail 按钮是薄接线（端点路径已 e2e），按钮本身未做 UI 自动化验证。

### 期 4 补二：API 面收口（2026-07-30 追落）

评审意图识别 API 面后修掉三组维护坑（A1/C1+C2/D1）：

- **入口约束归出生地（A1）**：clips-media 门从 answer 端点（无条件）与 `/generate`（仅 full scope）两处摘除，收进 `create_run` 本体（无条件——targeted 重渲染同样读源媒体，无 scope 豁免）；mode② requires 校验本就在此。三条起 run 入口（`/generate`、task_book start、chat 派发）从此只装配 TaskSpec，新增入口约束只需改一处。`create_run` 的 ValueError → 请求层 422（顺手修了 targeted scope 坏 target_id 原先裸 500），chat 层沿用 `except (SkillRejected, ValueError)` 反问兜底。
- **AnswerRequest 判别联合 + 消灭魔法 "start"（C1/C2）**：`start` 升为一等 answer kind（`AnswerPayload.kind` 加入），取代期 1 的魔法 `option_id="start"`；`AnswerRequest` 改为按 `kind` 判别的四态联合（option/freeform/start/bail，`extra="forbid"`）——`autonomy`/`intent` 只存在于 `start`，其他 kind 带 kind 外字段 422 而非静默忽略。kind × question-kind 契约显式化：task_book 只接受 start/bail，其他问题不接受 start（均 422）。前端 Start 按钮、`mark_task_book_started`、`QaPair` 同步；QA 展示保留旧拼写（`option`+`option_id="start"`）分支兼容历史行。
- **create_run 事务边界（D1）**：内部 `commit()` 改 flush——run、启动它的 answer、`project.pending_intent=None` 落在同一请求事务，消灭"answer 已提交 + run 已建 + pending_intent 残留"的三方不一致窗口；run 只在请求提交后才可被 worker 认领。三个调用点（`/generate`、answer 端点、chat 派发）本就有尾部 commit，语义不变；手工脚本需自行 commit。
- **验证**：判别联合行为（start/option/缺 id 422/带外字段 422/未知 kind 422）脚本实测 ✅；纯函数套件 28/28 ✅；前端 tsc ✅；`/generate`+task_book start 双路径 e2e（真实 API+worker）✅。

### 期 4 补四：意图覆盖缺口清扫（G-1/G-4/G-2 + G-5/G-6 收编）（2026-07-30 追落）

按 `INTENT_COVERAGE.md`（覆盖穷举母表）清扫登记表缺口：修 G-1/G-4/G-2，G-3 明确不做，G-5/G-6 随 G-4 的 answer 形态收编。

- **G-1 确认相位原话确认直接起 run**：`InferredIntent.action` 加第三值 `"start"`（LLM 判定确认意图——"looks good, start it"/"好的开始吧"——时返回；prompt 写死"确认不是修订"+ 累积 prompt 以末行定 action）。`/intent` 路由新增 start 分支：**不复制起 run 逻辑**——`record_intent_turn` 原话入档后找到会话待决 task_book 问题，调 `answer_question(db, uid, q.id, StartAnswerRequest(kind="start"))`（run 唯一起源地 create_run 与 answer=resume 语义不变，pending_intent 由 answer_question 同事务清除）；响应联合加第三态 `ProjectIntentStartedResponse{type:"started", run_id, answered_question}`（`started` 取结果报告读法，Stripe `succeeded`/GitHub `completed` 同款过去分词，与动作词 `kind="start"` 分工）。无可启动对象时不覆盖 stored 任务书：有存量书 re-dock 原样返回 plan，无则降级 generate（answer 哑弹的孪生处理）。纯谓词 `is_pending_task_book` 进 service。前端 `GenerationOverlay` 两处 /intent 消费点（sendPlanRefinement + fallback fetch）处理 `type==="started"`，`IntentTurnResponse` 联合类型落码；"run 启动落位"（QA 入档 + 清 dock + setRunId + phase running）三处归一为 `landOnStartedRun`。不做前端正则匹配确认话术（多语言脆弱，语义判断正是 LLM 该干的）。**复审补（R-1）**：`ProjectIntentRequest.autonomy` 透传——review 档用户先切档再打字确认时自治档不静默掉回 auto（聚焦 e2e：`/tmp/e2e_g1_autonomy.py`，started + run.context.autonomy=review + checkpoint 拓扑物化 + 优雅 bail，全绿）。
- **G-4 ChatIntentAgent 第四态 answer（N-21）**：`AnswerProposal{type:"answer", text}` 进判别联合——纯信息直答（能力/进度/解释/闲聊），不落 task、不起 run、不 dock 问题，落普通 assistant 消息（与 B1 answer 回合同款存档形状）。`_propose_turn` 加分支。agent prompt 边界写死：answer 只在无工作请求且无歧义时用；要干活 → task_list/edit_ops；读数有歧义 → ask；进度问题凭节点级进度段照实答不准瞎编。**G-5/G-6 收编**：发布意图 → answer 引导产物卡发布按钮；品牌/说话人修改 → answer 导航 Brand template / Speakers 页面（answer 是 LLM 自由文本，按用户语言生成，与现有 assistant 消息一致，不走 i18n 键）。
- **G-2 进度询问的节点级数据**：`_build_context` 在 latest run 行后注入 steps 量化摘要——纯函数 `_format_step_progress`（每步一行 `kind: status — summary`，≤12 行，超出截尾带省略行；waiting checkpoint 行天然传达"在等你"，槽标签如 "Post · DE" 随 summary 同行）。零新机制，纯 context 丰富化。
- **顺手修正（真坑）**：`_validate_requires` 的 transcript 检查漏了 `extracted_text`——txt/md 文档型转写资产落 `extracted_text`（消费侧 `project_context.py` 本来就 prefer 它），mode② 派发却对纯文档项目一律拒 "Missing required input: transcript"。对齐消费规则补进 or_ 条件（e2e 里真实抓到：chat 派发 write_post 被拒）。
- **e2e 实录**（真实 LLM + 真实队列，`/tmp/e2e_g124.py`，12/12）：① confirm 相位 "Looks good, start it." → `type=started`、run 已建、task_book 题 answer.kind=start 且带 workflow_run_id、pending_intent 清空、用户原话单行入档（去重）✅；② /chat 发布问题 → answer 形态（无 run、无 dock、run 数不变，引导文案指向产物卡发布按钮）✅；③ running 中 "How far along is the generation?" → answer 照实引用节点状态（preprocess done、persona/understand running、逐槽 post_gen 标签可见）✅；④ 回归：修订 → plan 重 dock + 旧题 supersede ✅；派发 "write a French article" → task_list 新 run 并跑完 ✅；模糊工作请求 → choice dock ✅；autoResume 答题 ✅。两 run 均 completed；e2e 数据清理含 Speaker。
- **LLM 行为实录（值得留档的裁决）**：请求 run 已覆盖的产物（"再写个德语帖"而 run 里已有 post(de) 槽）→ answer 指认在跑步骤而非重复派发——G-4 + G-2 组合出的理想行为，e2e 场景已据此改写为请求未覆盖产物。
- **运维**：orchestrator 改动后已全杀重启常驻 worker（`ps aux | grep app.worker` 数清零再起，起完恰好两条）；API uvicorn --reload 自动捡 intent/service/schemas 改动。
- **文档**：INTENT_COVERAGE 缺口表 G-1/G-4/G-2/G-5/G-6 翻 ✅ + 矩阵/通道图/测试矩阵同步；CHAT_ARCH §3 四态契约 + §8.5 /intent 联合三态 + §6 context 表；NAMING N-21 判例 + 回答词汇行（落库态 kind 补 start + 提议态 AnswerProposal）。
- **验证**：纯函数套件 44/44（+14：`_format_step_progress` 5、`is_pending_task_book` 4、`AnswerProposal` 联合 3、`InferredIntent` start 2）；前端 tsc ✅。

### 期 4 补三：B 组契约形状收尾（2026-07-30 追落）

API 面评审 B 组（形状债）+ C3 一次扫掉，e2e 13/13：

- **B1 answer 回合落库 + 响应判别联合**：`/intent` 返回 `{type:"plan", intent, reasons} | {type:"answer", text}`——能力问答的双方落普通消息行（`record_intent_turn`，对最新 user 行去重防刷新双写），确认相位对话从此遵守"一切皆消息行"；**顺手修了真 bug：answer 回合原先会覆盖 stored 任务书**（pending_intent 被写成 answer 动作的垃圾默认书，之后点 Start 会跑错计划）——现在 answer 回合不写 pending_intent。请求体加 `turn`（refinement 发累积 prompt 推理、只把本轮新行入档）。overlay 开屏重放会话历史（ seeded 首 prompt 跳过——它由 prop 带附件渲染；待决问题进 dock 不进流）。
- **B2 信封对齐**：`AnswerResponse{message, follow_up}` → `{answered_question, follow_up}`，与 `ChatResponse.answered_question` 同角色同名；前端三处调用点同步。
- **B3**：`/generate` 响应裸 dict → typed `GenerateResponse{run_id, status}`（全 API 唯一无 schema 出口消灭）。
- **B4**：`needs_clarification` 从响应与 `PendingIntent` 双处摘除（`reasons.length > 0` 可推导）；存量行靠 before-validator pop 旧键读取容忍。前端 `initialNeedsClarification` 改 reasons 推导。
- **C3 count 边界**：`SLOT_COUNT_LIMITS`（clips 1-10 / quotes 1-20 / carousel 2-15，镜像面板自带限制）进 `create_run` 出生地校验——count=999 烧钱的洞堵死；post/article 不带 count（一槽一产物，要多加槽）。未知 slot type 本就被 `IntentSlot.type` Literal 挡在 schema 层。
- **验证**：e2e 13/13（C3 两种越界 422、plan/answer 双回合落库+去重、answer 回合不覆盖任务书、B2 信封、B3 形状、B4 双处无字段）；纯函数套件 28/28；tsc ✅。
- **复查再修三处（同日）**：① answer 动作但 answer 文本为空的 LLM 哑弹会走 plan 分支把 answer 动作的垃圾书写进 pending_intent——分支前归一化为 generate（与旧前端行为一致）。② 空 options 的 freeform 问题接受 option 答案不校验——补 422。③ **MiniMax 裸 `httpx.HTTPStatusError` 穿透全部降级路径**（client 三处 `raise_for_status` 从不包装，402/429/5xx 直达 500；e2e 中真实抓到一次 402）——client 边界统一 `_raise_for_status` 包装成 `MiniMaxError`，agent 默认书/chat 反问兜底从此真的兜得住；纯函数套件 +2（30/30）。

## 期 3 落地实录（2026-07-30）

- **AskProposal 第三态**（`schemas.py`，N-18 落代码）：`{type:"ask", question, kind, options, allow_freeform, cost_hint}`，`kind = choice|task_book|confirm`（confirm 座位留给成本 quote）。判别联合升三态；N-14 的 "tasks=[] 反问" 在 service 层迁移为 options 空 + allow_freeform 的 ask 落库。
- **ChatIntentAgent prompt**（`intent.py`）：shape C 规则（choice / 2-4 选项 / 字母 id / freeform 回落；kind 永远 choice——task_book 由 /intent 代码路径发，confirm 预留）；shape A 改 tasks 非空；rules 加"待决问题在下文时，用户消息可能是其答案"。
- **ask 落库 = `_dock_question()`**：task_book 同步、AskProposal、tasks=[] 迁移三路共用；单待决不变量（新题落库旧题 auto-bail `superseded`）。chat ask 落库时 kind 裁决为 choice（LLM 提议、代码裁决）。
- **answer 分派**（`answer_question`）：choice + option/freeform → 记录后续聊——answer 端点即恢复（NAMING §2），option 答案回填 label 进 `answer.text`（QA 入档显示人话不是裸 id）；返回 `(message, follow_up)`，路由响应换 `AnswerResponse` 信封。choice bail 只记录。
- **确定性 autoResume**（`chat()`，零 LLM，禁 #4）：choice 待决时自由文本 → `_match_option` 命中字母(id)/序号(1-based)/原文 label → option 回答；否则 allow_freeform → freeform；否则按新 intent 处理、问题保持待决。**task_book 待决不参与 autoResume**（它的答案是 dock 的 Start/Cancel 与 /intent 修订）。
- **续聊共享 `_propose_turn()`**：从 `chat()` 抽出的"单轮提议-裁决-记录"核，choice 续聊与 POST /chat 共用；`_build_context` 带 QA 答案行（"the user answered: …"）+ 待决问题段（含选项清单）。
- **`ChatResponse.answered_question`**：autoResume 本轮回合掉的问题行，前端据此 QA 入档。
- **入口 reasons → question 消息**（`projects.py`）：`sync_task_book_question` 带 reasons 参数，task_book 问题人话原文追加 `(needs your check: …)`（数据存键，渲染时本地化）。
- **前端**：`QuestionDock` 改 kind 判别单组件（N-19 禁用途×机制组合词——无 ChoiceDock 新词）：task_book 形态加 reasons 提示行；choice 形态 = ✓+问句+选项按钮组（字母徽章镜像 autoResume 映射，costHint 解剖位预留）。GenerationOverlay 待决获取扩到全相位（choice 在 running 相位复活）、`answered_question` QA 入档、follow_up 续聊入流/链式 dock、input 占位 "Something else…"（choice 待决 + 有选项 + allow_freeform）、`initialReasons` 接线（$id.index.tsx 传 pending_intent.reasons，/intent 响应逐轮刷新）。ChatModal 同套：会话加载带 pending_question、dock 置顶 input 上方、QA/链式同构。
- **顺手修正（真坑）**：`messages.question/answer/intent` 改 `JSONB(none_as_null=True)` / `JSON(none_as_null=True)`——期 1 `_create_message` 显式传 `question=None` 按 SQLAlchemy JSON 默认绑成 `'null'::jsonb`（JSON null 非 SQL NULL），`question IS NOT NULL` 谓词会把普通消息误判为待决（仅当非问题消息最新时触发，期 1 e2e 未踩中）。dev 库 73 行历史消息全部 SQL NULL 无需清洗。
- **e2e 实录**（真实 LLM，验收条目 5）：模糊指令出选项卡（4 选项 + allow_freeform）✅；字母 "a" → option 命中 QA 入档续跑（label 回填）✅；序号 "2" ✅；原文 label ✅；非命中自由文本 → freeform 原文入档 ✅；点选 answer 端点 → {message, follow_up} 续跑 + 链式 dock ✅；单待决 supersede（新题落库旧题 bail:superseded）✅；待决重建（GET conversation 带 pending_question+options）✅；task_book 待决不被 chat 文本吞 ✅；入口 reasons 进 task_book 人话原文且取代开口 choice ✅。answer-action 回合不起 task_book（期 1 行为原样）。
- **偏离简报处**：choice 续聊的 follow_up 复用 `_propose_turn`（简报说"记录并续聊"，实现为 answer 端点内联续跑而非前端再发一轮——与期 4 checkpoint 唤醒同机制位）；`_dock_question` 收敛三路落库（简报只点名 service 分派）；dock 未加 freeform 提示行（占位符已传达，避免重复文案）。

## 期 1 落地实录（2026-07-29）

- **迁移** `e9f4c2a81d63`（head 接 `d7e3b1a95c42`）已应用：question/answer JSONB nullable。
- **answer 端点** = `POST /api/v1/chat/messages/{id}/answer`；待决查询 = `latest_pending_question`（会话最新未答 question，GET `/chat/conversation` 带 `pending_question`）。
- **task_book 分派**：bail → 清 `pending_intent` 回 draft（"可重开"= 重走 /intent，prompt 已 seed 进会话）；start → 从 pending_intent 起 run 并写 `workflow_run_id`。
- **autonomy 提前接线**（期 4 行为不变）：`AnswerRequest`/`GenerateRequest`/`TaskSpec` 三处加 `autonomy`（默认 auto），随 run.context 落库；compile_graph 零改动。
- **supersede 编码**：refinement 产生新问题时旧问题 auto-bail，`answer.text="superseded"` 为机器标记；前端按 kind+text 本地化（started/cancelled/superseded）。
- **/generate 兜底 settle**：直接走 /generate 的调用（auto-start 回退、重试、API 调用方）经 `mark_task_book_started` 把开口 task_book 问题答成 start——两路径共用"一行一答"不变量。
- **顺手修正**（同文件评审发现）：`has_renderable_media` 抽到 `asset_processing.py`（/intent、/generate、answer 三处共用，消灭第三份拷贝）；`seed_project_prompt` 改幂等（代码对齐旧注释"已有消息则 no-op"，/intent 提前 seed 后 /generate 不再重复落 prompt）。
- **前端**：`QuestionDock.tsx`（✓+问句+Auto/Review 下拉+Cancel/Start+leaveNote）；`QaPair.tsx`（QA 双层 + `qaAnswerText`）；GenerationOverlay 计划卡决策移入 dock（卡只留审阅面板）、refinement 后重取问题行、auto-start 等 questionLoaded、运行态 QA 对/摘要卡双路径；ChatModal QA 变种 + 待决过滤（禁 #2）；i18n `questionDock.autonomy.*`/`chat.qa.*` en/zh；`decideLater` 键退役。
- **e2e 实录**：bail→draft 可重开 ✅、QA 三形态入档 ✅、refinement 取代 ✅、重复回答 409 ✅、autonomy=review 落 run.context ✅、/generate 兜底+幂等 seed ✅（空素材 run 失败属合成项目预期）。
- **偏离简报处**：期 1 未新增 `TaskSpec.autonomy` 以外的 orchestrator 改动（简报 §3.7 的 Suspend/finalize 谓词归期 4 原样）；choice/checkpoint 的 answer 只记录不分派（期 3/4）。

## 期 2 落地实录（2026-07-29）

- **IntentSlot schema**（`schemas.py`）：`{type, count, focus, language, tone_override, explicit}`；`SLOT_DEFAULT_COUNT`（clips 5 / quotes 3 / carousel 6）单点定义。遗留容错以 `model_validator(mode="before")` 落在 `IntentSlot`（裸 type 字符串→裸槽）与 `InferredIntent`（旧扁平 pending_intent 读时升级 + 退役键丢弃）——只读容错，非过桥层。
- **全链路换形**：`InferredIntent.outputs: list[IntentSlot]`（退役 clip_count/quotes_count/carousel_count/clip_count_explicit）；`GenerateRequest.slots`（退役 outputs + 三个扁平 count，422 语义不变）；`TaskSpec.outputs: list[IntentSlot]`；run.context 原样落槽形状。
- **compile_graph per-slot 扇出**：canonical 排序（类型序→请求序，`ordered_slots()`，clips 单槽去重——clips_pipeline 的全量重剪语义假设单 clips 节点）；一槽一 executor 节点，spec 携带 `slot`（原样）+ `slot_index`（同类内序号）；带 language/focus 的槽在物化时预设 `spec.summary` 标签（"Post · DE"），兄弟节点在 stepper 里立即可分（不动步骤数据结构，禁 #14）。
- **语言解析** = `slot.language ?? node.spec.target_language ?? run.target_language`（`run_derivative_gen`/`run_clips_pipeline` 同规则）；`_node_slot()` 先从 node.spec.slot 取，mode②/targeted 回落 ctx 同类首槽。
- **幂等删除兄弟安全**（`run_derivative_gen`）：删同类型且 `workflow_step_id ∉ 本 run 同 kind 节点集合`（含 NULL step 的旧产物）——两 post_gen 并发互不误删，DB 级验证通过。clips 单槽不受影响。
- **director_plan 逐槽透传**：task_book = `{slots, target_language}`；`_align_storyboard_slots()` 把 LLM 返回的 storyboard 槽按类型+顺序 1:1 对齐到任务槽，显式字段（count/focus/tone_override）代码兜底覆盖，空缺槽补 `StoryboardSlot(slot=type)`——显式不可违背从 prompt 规则升为代码保证；executor 经 `slot_index` 收窄 storyboard 到本槽（`_find_slot` 零改动）。
- **pin 合并**（`chat/service.py: merge_explicit_slots`）：匹配键 (type, language)；explicit 槽原样替换同键新槽，新推断丢弃的 explicit 槽重新补回；`/intent` 路由从 `ProjectIntentRequest.prior`（面板手编）或已存 pending_intent 取 pin 源。
- **answer 携带手编任务书**：`AnswerRequest.intent` 可选——dock Start 把面板编辑后的整本书送进 run（修补了期 1 面板编辑在 dock 路径被丢弃的缺口）；缺省回落已存 pending_intent。
- **前端**：审阅面板换逐槽行（类型 + count 步进器 + focus 行 + language 下拉，手编置 explicit；可加/删槽，clips 禁重槽）+ 身份回响行（speaker/brand 名单次解析，只读）；planSummary 逐槽；`normalizeSlots/normalizeIntent` 双形状容错（老 run.context 扁平形状展示容忍）；refine 携带 `prior`、Start 携带 `intent`；retry 换 slots 契约；i18n en/zh 换形（退役 outputDescs/clipCount*/planSummary*，新增 slot 编辑/身份回响键）。
- **e2e 实录**：条目 2 ✅（真实 LLM：en/de 两 post 槽一次 run、德语帖德语、storyboard 两槽论点互补 a1-a5/a5-a8、兄弟产物共存）；条目 3 ✅（"切片剪定价争议、帖子写总结、8 张金句卡" → clips.focus=定价争议 / post.focus=全场总结 / quotes.count=8，j2 渲染显式标记可见）；条目 4 ✅（quotes count=7 explicit 在 re-inference 后保留，其余按新推断；answer 携带后 run.context 落 7）。
- **注意**：本机常驻 worker 需重启才加载新代码（旧码 worker 执行槽形状 run 会退化：director_plan 读不到 outputs 落 clips 兜底）。
- **偏离简报处**：`slot_index` 进了 node spec（简报未点名，是 executor 找本槽 storyboard 的机制位）；explicit 槽的 pin 粒度 = 整槽保留（简报"该槽 count 保留，其余按新推断"的实现读法：整槽 pin 是结构化最小单元）；审阅面板加了增/删槽能力（旧 pills 的等效能力，否则退化为不可改 outputs）。

## 0. Context

意图层有两个结构性病灶：

1. **扁平参数袋**：`clip_count` → `quotes_count` → `carousel_count` 发现一点改一点，且用户无法差异化对待不同产物。四个真实场景判了它死刑：
   - ① **分产物角度**："切片剪定价争议、帖子写全场总结、金句挑远程团队"——一个全局 instruction 刷所有产物，LLM 只能猜分配。
   - ② **同类产物多语言**："英文 LinkedIn 帖 + 德语帖"——`outputs` 类型枚举 + 全局单一 `target_language`，**一次 run 在结构上不可能**；绕法（两次 run）产物撞角度，像孪生草稿而非互补资产。对欧洲 ICP 这是入场券场景（CLAUDE.md：多语言是入场券）。
   - ③ **分产物语气**："帖子正式、金句活泼"——分镜槽位早有 `tone_override`/`cta` 字段，意图层够不着。
   - ④ **修改牵一发动全身**：re-inference 全量重推断，"金句改 6 张"可能悄悄改掉已确认的"德语"——pin 纪律需要数据结构保证。
2. **确认盲**：确认面是一张混在消息流里的参数卡片，用户在系统展示任何素材理解之前做承诺。

2026-07-28/29 两轮设计评审结论：用户发完提示词需要被理解的证据、可预期的交付、花钱前的低成本修正通道；确认有光谱（参数→方向→身份→负空间）；问话有纪律（拦/回显/邀请/永不问）。Opus Agent UI 实证了形态（research §9）：**审阅面板在消息流里可编辑，决策条停靠 input 正上方；选项卡提问、QA 双层入档、best-judgment 兜底文案**。Mastra 提供机制语义参照：suspend/resume/bail 三动词 + 双向 typed 载荷 + 存储Backed 待决重建。

## 1. 已核实的现状事实（读码确认）

- **IntentProposal 二态判别联合**（`schemas.py:180-227`，N-14）：`tasks=[]` = 反问，summary 装自由文本；ask 无 typed payload 座位。
- **分镜表已是 slot 形状**（`director_plan.j2`：`slot/focus/argument_ids/quote_candidates/cta/tone_override/count`）——下游早就会说槽位语言，是意图层的扁平让用户够不着已有结构。
- **任务书全链路扁平**：`InferredIntent.outputs`（类型枚举）+ 三个 count 字段 → `GenerateRequest` → `TaskSpec.outputs: list[str]`（`orchestrator.py:57`）→ run.context。`compile_graph` 按**类型**扇出 executor（一种产物一个节点，`orchestrator.py:110-115`）；`run_derivative_gen` 幂等语义 = 删该项目同类型全部旧产物（`node_runners.py:1104`）。
- **mode② 回填**：`_backfill_context`（`orchestrator.py:246`）从 task items 推导 outputs/clip_count 补 mode① 上下文字段——slot 化需同步改。
- **`waiting` 座位已预留**：`StepStatus` 含 `waiting`（`schemas.py:1081`，注释明写 `spec.suspend_payload`）；`WorkflowStatus.WAITING_HUMAN` 枚举已存在（`schemas.py:102`）全库无引用。
- **finalize 两处谓词不含 waiting**（必改）：`maybe_finalize_run` active 谓词（`orchestrator.py:476-480`）；`finalize_stuck_runs` SQL（`orchestrator.py:514-525`）——waiting 节点会让 run 被提前收官/被崩溃恢复扫掉。
- **Message 表**（`tables.py:360`）：无 question/answer 列；`intent` JSON 列已在（IntentProposal dump/轮）。
- **pending_intent 持久化已落地**（b61260d）："待决"存储语义就位。
- **计划卡钉在消息流上方**（非 input 上方）：GenerationOverlay "Conversation below the pinned regions"。
- **QualityBounce（quality 期 3 设计）验证了暂停-恢复图机语义**：重置 pending + spec 载荷 → 自动重认领。checkpoint 复用同地基，区别是等人（停 `waiting`）不是等重跑。
- **问话纪律雏形已存在**：needs_clarification + reasons（`projects.py:305`），确定 auto-start（`GenerationOverlay.tsx:401`）。
- **方向选项原料已存在**：`MaterialUnderstanding.key_arguments`——checkpoint 选项代码派生，零 LLM。
- **run.context 老行是扁平形状**：只读历史（前端展示容忍双形状）；runners 只读本 run 新上下文，无回填负担。

## 2. 设计论证（评审沉淀区）

### 2.1 确认光谱与四层确认面

| 层 | 内容 | 落点 |
|---|---|---|
| 素材回响 | "我看到 47 分钟视频 + 一份 PDF" | 入口首条 assistant 消息 |
| 任务书审阅 | **逐槽** outputs/count/focus/language 可编辑面板 | 消息流内面板 |
| 身份回响 | "以 Anna 的口吻、大学品牌模板" | 面板内一行，不再询问 |
| 方向预览与确认 | understanding 核心论点 → 方向选项 | checkpoint（期 4，Review 档） |

### 2.2 停靠法则与 question 一行两态

> **消息列表是"已决"的历史，输入框上方是"待决"的现在。**

- 待决问题（task_book 确认 / 选项卡 / 成本 quote）永远停靠 input 正上方的 **QuestionDock**；同一时间最多一个待决（并发时 dock 显示最早未答，其余排队）。
- 回答瞬间坍缩成 **QA 双层消息**入档。
- 数据模型一行两态：`messages.question` JSONB + `messages.answer` JSONB nullable（**NULL = 待决**，宪法 §4）；`content` 存问题人话原文（自然进 LLM 上下文历史）。
- 待决重建零内存态：查会话最新未答 question（Mastra `listSuspendedRuns` 同款，靠消息行免费得到）。

### 2.3 提问机器（IntentProposal 第三态，翻案 N-14）

```jsonc
{
  "type": "ask",
  "question": "这五个切片你想做成哪种方向？",
  "kind": "choice",                 // choice | task_book | confirm（成本 quote 预留）
  "options": [{"id": "a", "label": "…"}, …],
  "allow_freeform": true,
  "cost_hint": null
}
```

- **翻案 N-14**：结构化 ask 的 payload 与 task_list/edit_ops 正交，判别联合加第三态；原"tasks=[] 反问"全部迁移（纯文本反问 = options 为空 + allow_freeform 的 ask）。
- **answer 契约**：`{kind: "option"|"freeform"|"bail", option_id?, text?, answered_at}`。
- **bail 是一等公民**：入口 bail = 回 draft 可重开；checkpoint bail = 下游级联 skipped、run COMPLETED（注明用户中止）。**永不标 failed**。
- **autoResume（确定性版）**：待决中用户发自由文本 → 命中选项 label/序号字母 → option；否则 allow_freeform → freeform；否则按新 intent 处理、问题保持待决。零 LLM；语义级映射归后续。

### 2.4 命名：机制词与用途词分离（Mastra 参照）

机制一词一物：`Suspend` 异常 / `waiting` 状态 / `answer` / `bail`；用途住 payload kind（direction/task_book/cost quote），**用途×机制组合词永禁**。状态词从机制动词派生；配对词整体引入（ask/answer/bail）。resume 不显式命名——答案端点即恢复。复用不造词：`explicit`（=pinned）、cost quote（v3）、`suspend_payload`（座位注释同款）。

### 2.5 任务书 slot 化（期 2，本轮解冻）

**形状**：

```jsonc
IntentSlot = {
  "type": "clips" | "post" | "quotes" | "carousel" | "article",
  "count": null,          // None = 默认（clips 5 / quotes 3 / carousel 6）
  "focus": null,          // ① 分产物角度（用户/意图识别）
  "language": null,       // ② None = 任务书级 target_language；同类型不同语言 = 多槽
  "tone_override": null,  // ③ 直通分镜槽同名字段
  "explicit": false       // ④ 用户手编标记（pin 合并规则用）
}
```

- **分层命名**：IntentSlot = **任务槽**（请求层，用户要什么）≠ StoryboardSlot = 分镜槽位（派工层，导演怎么排）。同名不同物禁令要求分层词。
- **全链路换形**：`InferredIntent.outputs: list[IntentSlot]` → `GenerateRequest` → `TaskSpec.outputs`（run.context 原样落库）→ task_book。**quality 期 1 的三个扁平 count 字段随之全库退役**（InferredIntent/GenerateRequest/TaskSpec/前端 wiring）。
- **拓扑变化：per-slot 扇出**。`compile_graph` 从"一种类型一个 executor 节点"改为"一个槽一个节点"——两个 post 槽（en/de）→ 两个 post_gen 节点，spec 携带本槽。语言解析 = `slot.language ?? run.target_language`。
- **幂等删除的兄弟撞车修复**：`run_derivative_gen` 现行"删该项目同类型全部旧产物"在多 post 节点的同一次 run 里会误删兄弟节点的新产物。改为：**删同类型且 `workflow_step_id` 不属于本 run 的该类型节点集合的旧产物**（clips 单槽不受影响）。
- **director_plan 槽规则**：任务书逐槽给出（count/focus/language 显式值）；director 只补空缺（argument_ids/quote_candidates/cta），**显式槽字段不可违背**；两 post 槽的论点分配必须互补（写进 prompt 规则）。
- **优先级**：`slot.focus`（用户显式）> checkpoint 方向（期 4）> director 自排。
- **pin 合并规则**：手编过的槽字段（`explicit: true`）在 re-inference 后被保留，新推断只填空缺——④的结构化解。
- **`_backfill_context` 兼容**：mode② task items → 槽形状回填（type 从 skill、count 从 params）。
- **零表迁移**：全在 JSON 载荷层；run.context 老行扁平形状仅前端展示容忍，后端无回填。

**与 quality 期 1（1148004，已落地）的对账点**——该 commit 中将被本迭代更新的位置：

| quality 期 1 触点 | 本迭代动作 |
|---|---|
| `schemas.py` `InferredIntent.quotes_count`/`carousel_count` | 退役 → `IntentSlot.count` |
| `schemas.py` `GenerateRequest` 两个 count 字段 | 退役 → slots 契约 |
| `orchestrator.py` `TaskSpec.quotes_count`/`carousel_count` | 退役 → `outputs: list[IntentSlot]` |
| `node_runners.py` `run_director_plan` 任务书 count 透传 | 换逐槽透传（count/focus/language） |
| `prompts/director_plan.j2` count 规则（显式优先/缺省 3/6） | 换槽规则（显式槽字段不可违背 + 同类多槽互补） |
| `intent.py` ComposerIntentAgent 两个 count 识别规则 | 换逐槽识别（含同类多语言多槽） |
| `GenerationOverlay.tsx` / `$id.index.tsx` count wiring + `planSummaryQuotes/Carousel` | 换逐槽编辑面板（i18n 键同步换形） |

不动（期 1 成果原样保留）：锚点转写、`quality.py` 六函数、四个 prompt 修正、loudnorm。

### 2.6 checkpoint 节点（方向检查点，期 4）

独立节点 kind，**瘦节点规则**——提问前不做重活（队列式重入：答案回来后从 runner 顶上重跑，靠 spec.answer 分支直达 done；不是 Mastra 的调用栈续跑）。

```
director_understand(3) → checkpoint(3.5, spec.for=direction) → director_plan(4) → executors…
```

- 被认领：从 understanding.key_arguments 派生选项（≤3 个"聚焦：{论点}" + "全场高光"默认 + freeform）→ 写 question 消息 → 转 `waiting`（`spec.suspend_payload` 存选项）→ run 转 `WAITING_HUMAN`。
- 答案到（`POST /messages/{id}/answer`）：spec.answer 写入、节点回 pending、run 回 RUNNING → 重认领 → done，summary = 选定方向。
- `director_plan` 消费：option → priority argument_ids；freeform → focus 指引文本；默认 → 现状行为。与槽 focus 的关系见 §2.5 优先级。
- **bail**：节点 done（spec.bailed）+ 下游级联 skipped（`_cascade_skip` 非失败变体）+ run COMPLETED。
- **finalize 两处谓词补 waiting**（§1 已核实）。
- **不进 SKILL_REGISTRY**（verify 判例同款）。

### 2.7 自治档 autonomy

- `TaskSpec.autonomy: "auto" | "review"`（默认 auto，随 run.context 落库）。
- auto：只硬阻塞（clips 无媒体、语言必错类入口拦截）——现状行为，零新增打断。
- review：full run 在 understand→plan 间插 direction checkpoint；targeted run 不插。
- UI：dock 决策条内 Auto/Review 切换（Opus 同款位置），随本次 /generate 提交。
- 兜底文案："计划已保存，离开不中断——我会按最佳判断完成，随时回来看看"。

### 2.8 明确不做（本期）

- **transcript 纠错确认**——归术语表线（ROADMAP §6，查找替换式 + 固定译法/发音两消费者）。
- **成本 quote**（confirm 形态 + cost_hint 解剖位已预留）——CHAT_ARCH v3。
- **per-slot cta**（CTA 归 speaker 级/全局 instruction）与 per-slot tone 的**编辑 UI**（`tone_override` 字段进 schema，由意图识别填充；手编 UI 归后续）。
- **LLM 语义级 autoResume**、多待决并行、per-output 检查点、verify needs_human 主动 ask 版、@picker。

## 3. 后端改动点

1. `app/models/tables.py`：`messages.question` / `messages.answer` JSONB nullable + alembic 迁移。
2. `app/models/schemas.py`：`IntentSlot`；`AskProposal`（第三态）；question/answer payload schema；`InferredIntent.outputs` → `list[IntentSlot]`（退役三个扁平 count）；`GenerateRequest` 换 slots；`TaskSpec.outputs` → `list[IntentSlot]` + `autonomy`；ChatResponse 带 pending question。
3. `app/chat/intent.py`：ComposerIntentAgent 产出槽（count/focus/language 逐槽识别，含"英德两版帖"同类多槽）；ChatIntentAgent prompt 加 ask 形态规则；context 组装带待决问题。
4. `app/chat/service.py`：ask 落库；answer 处理分派（task_book → 更新 pending_intent/起 run；choice → 续聊；checkpoint → 唤醒节点）；确定性 autoResume；待决查询；**pin 合并**（explicit 槽字段在 re-infer 后保留）。
5. `app/chat/routes.py`：`POST /messages/{id}/answer`；GET conversation 带 pending_question。
6. `app/pipeline/routes/projects.py`：/generate 换 slots 契约（422 语义不变）；needs_clarification reasons → question 消息（期 3）。
7. `app/pipeline/orchestrator.py`：`Suspend` 异常 + execute_step 捕获分支 + answer 唤醒 + bail 级联；finalize 两处谓词补 waiting；`compile_graph` per-slot 扇出 + autonomy 裁决 + `_backfill_context` 槽兼容。
8. `app/pipeline/node_runners.py`：`run_checkpoint`；`run_director_plan` 任务书逐槽 + 消费 checkpoint answer；executor runners 读 `node.spec.slot`（count/focus/language）；`run_derivative_gen` 幂等删除改兄弟安全。
9. `app/prompts/director_plan.j2`：槽规则（显式字段不可违背；同类多槽论点互补分配）。

## 4. 前端改动点

1. `QuestionDock.tsx`（新）：停靠条常驻 input 正上方；解剖 = ✓ + 问句 + cost_hint? + 按钮组（含 bail）；choice 形态渲染选项按钮组；task_book 形态渲染决策条（开始/取消 + Auto/Review 切换）。
2. 任务书审阅面板：**逐槽行**（类型 + count 步进器 + focus 行 + language 下拉），Start 决策移入 dock；身份回响行；老 run.context 扁平形状展示容忍。
3. input 变种：choice 待决时占位提示 "Something else…"；自由文本走 autoResume。
4. QA 消息渲染变种（Q/A 双层）。
5. 步骤流 waiting 行 + run waiting_human 展示；per-slot 扇出后同类型多节点的区分显示（节点带语言/角度标签）。
6. 离开提示文案行。
7. i18n en/zh 全套（dock/question/QA/autonomy/waiting/slot 编辑/离开提示）。

## 5. 命名审计（NAMING §5 触发）

新名词登记（§2 词汇表）：`IntentSlot`（任务槽：任务书一行 = 一个产物的请求，带 count/focus/language；**不是分镜槽位**——请求层 vs 派工层）、`ask`（提问，提议态）、`question`（问题，落库态）、`answer`（回答）、`bail`（弃做）、`Suspend`（挂起异常）、`checkpoint`（检查点节点 kind）、`autonomy`（自治档）。
退役：`InferredIntent.clip_count`/`quotes_count`/`carousel_count` 扁平 count 字段（quality 期 1 过渡形态，`IntentSlot.count` 取代，全库清除不留过桥层，宪法 §1）。
翻案判例（拟 N-18）：N-14"不加第三态"翻案——结构化 ask 升第三态，自由文本反问迁移为 ask 的 freeform 形态。
判例（拟 N-19）：机制词与用途词分离——用途×机制组合词永禁（Mastra 参照）。
判例（拟 N-20）：任务槽 vs 分镜槽分层——请求层与派工层各有槽位词，混用即违规。
启用座位不算新词：`waiting`/`WAITING_HUMAN`/`suspend_payload`。

## 6. 分期与验收

| 期 | 内容 | 行为变化 |
|---|---|---|
| 1 | messages 迁移 + answer 端点 + QuestionDock（task_book 形态）+ QA 渲染 + 离开文案 | 决策不再被滚走；可取消；离开有提示；刷新/跨设备 dock 复活 |
| 2 | **任务书 slot 化全链路** + 逐槽编辑面板 + pin 合并 | 逐产物角度/语言生效；"英德两版帖"一次 run；改一槽不动其他槽 |
| 3 | ask 第三态 + choice dock + autoResume + 入口 reasons→question | chat 出选项卡提问；答完 QA 入档；自由文本命中选项即映射 |
| 4 | Suspend + checkpoint + autonomy + finalize 谓词 + bail + waiting UI | Review 档生成中途停问方向；选/自由/弃做三路径 |

验收（e2e 为准，无测试套件纪律）：

1. **期 1**：长对话滚动确认条不动；Cancel 回 draft 可重开；QA 双层入档；刷新 dock 复活。
2. **期 2 多语言**："给我英文和德语两版 LinkedIn 帖"→ 一次 run 两个 post 产物、语言各自正确、storyboard 两槽论点分配互补、兄弟节点产物互不误删。
3. **期 2 角度/数量**："切片剪定价争议、帖子写总结、8 张金句卡"→ 槽 focus/count 进 director_plan prompt 可见；产物角度与之一致。
4. **期 2 pin**：手编某槽 count 后自由文本 refine → 该槽 count 保留，其余按新推断。
5. **期 3**：模糊指令出选项卡（非纯文本反问）；点选/字母/原文命中 → QA 入档续跑；非命中自由文本 → freeform 或保持待决，不静默吞掉。
6. **期 4 拓扑**：Review 档 full run 含 checkpoint；auto 档不含；targeted 不含。
7. **期 4 三路径**：选项 → slot focus/argument 分配体现；freeform → focus 指引含原文；bail → 下游 skipped、run COMPLETED 注明用户中止、不标 failed。
8. **期 4 韧性**：waiting 时 kill worker 重启 → 不被 finalize_stuck_runs 收官；答案到后正常续跑。
9. **成本**：checkpoint 节点零 LLM 调用。
10. **文档落地**：CHAT_ARCH §3 三态 + §8 dock/question 节；NAMING §2 登记 + N-18/N-19/N-20；ROADMAP 相应行更新。

## 7. 禁止行为（Prohibited Behaviors）

1. **禁** ReAct/多步推理——轮内单次调用铁律不动。
2. **禁**待决问题进消息流渲染——待决只在 dock，已决才入档。
3. **禁**多待决并行——最多一个未答 question，新题取代或排队。
4. **禁** LLM 生成 checkpoint 选项文案 / 语义级 autoResume——代码派生与确定性映射，LLM 版归后续。
5. **禁** bail 标 failed 或弹错误 toast——优雅退出是正常路径。
6. **禁** checkpoint/ask 进 SKILL_REGISTRY 或被 LLM 任务列表提议。
7. **禁**用途×机制组合词——用途住 `question.kind` / `spec.for`。
8. **禁**引 agent 框架、快照存储层、内存态待决。
9. **禁**新造 pinned/suspended 词——用已有 explicit / waiting。
10. **禁**扁平 count 字段与 slot 并存——全库退役不留过桥层（宪法 §1）。
11. **禁**任务槽与分镜槽混名、slot 化新增表列（全 JSON 载荷层）。
12. **禁** auto 档插任何可选检查点——自治档是用户偏好不是产品赌博。
13. **禁** transcript 纠错、成本 quote、per-slot cta、意图外的 slot 化扩散进本期。
14. **禁**前端 stepper 契约变更——只加 waiting 行样式与 question 渲染变种；同类型多节点靠标签区分，不改步骤数据结构。
