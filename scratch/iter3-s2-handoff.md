# iter-3 交接提示词（S2 半成品 → S9 收口）

> 用途：新开会话（零上下文）继续施工 Repurposer「Agent Working Loop 迭代三」。把本文件全文作为首条提示词粘贴即可。本文件本身不落 git（scratch/），施工状态以简报 Status 行 + git 为准。

---

## 0. 一句话任务

Repurposer「Agent Working Loop」三次迭代之**最后一次**（迭代三）：把一次性的「生成」收口为**持续工作闭环**——Plan→Confirm→Execute→Review→Revise→Discover-again，用户的每一次意图变化都落在产品语义层（候选/精选/方案/产物），永不碰 wiring/Task DAG 词汇。

## 1. 工作环境（先确认再动手）

- 工作目录（worktree）：`/Users/sylas/repurposer/.claude/worktrees/iter2-cut-segments`
- 分支：`feat/iter3-revision-loop`（已被本 worktree 占用——**直接在里面干，不要新开会 worktree、不要切分支**）
- api 命令 cwd：`apps/api`（一律 `uv run ...`）
- **共享 dev DB 警告**：本 worktree 与主 checkout 共用同一个 dev 数据库——跑 live 剧本/create_run 前先停掉旧栈（dev.sh 家族杀）；常驻 worker 会抢跑手工 run，验证后清数据（fixture 用 `scenario/` 前缀，永不共享 demo key）
- git stash 栈是多会话共享的：禁裸 `git stash`/`git stash pop`；必须用 `git stash push -u -m "<唯一tag>"` 并立刻记 SHA，恢复用 `git stash apply <sha>`
- 凭据永不打印、`.env` 永不提交
- commit 信息用 conventional commits，结尾带：
  `Co-Authored-By: Claude Code <noreply@anthropic.com>`

## 2. 必读清单（按序读完再动手，跳过 = 返工）

1. 仓库根 `CLAUDE.md`（项目协作规范——UI 戒律/文案律/测试例外/提交规范）
2. `docs/README.md`（docs 索引与治理）
3. **`docs/tasks/agent-working-loop-iter-3.md` —— 母合同**。§1 冻结条 8 条（违反任何一条 = 停下来问）、§3 E1~E10 拍板、§4 S0~S9 切片、§5 避让清单、§6 验证纪律。Status 行是当前进度的唯一事实源
4. `docs/DECISIONS.md` 的 ADR-088（探索产物 + 双状态机 + R6 发现路由 + R18 同框 + R23~R26 记忆分层）与 ADR-089（R12 编译出 LLM / R15 停顿定律 / R16 决策包 / R19 修订二分律 / R20 确认快照即路由器基材 / §8 迁移弧）
5. `docs/NAMING.md` N-58 词族（revise_output / revise_selects / run_review / get_artifact / plan_task_map / at+duration_ms / mark_compiled+supersede-继任——新词先登记再写码）
6. 迭代二简报 `docs/tasks/agent-working-loop-iter-2.md` 的 §5 避让清单（确认教义 / dock pill 唯一座 / G-1 / trigger turn 白名单 / 打字机律 / Activity 十规则 / R18 同框纪律 / reasoning 永不持久化）——全部继承冻结
7. `docs/MODULE_ARCHITECTURE.md` §7（表归属 + 队列机制）

## 3. 已完成切片（不要重做）

- **S0 ✅**（`1dce4c4`）：NAMING N-58 登记 + ADR-089 §8 select_clips 裁决销记 + PROGRESS 池挂账（「零探索退化形态」P1 条目）
- **S1 ✅**（`bf4d771`）：`CompiledScope{tasks, plan_task_map}` 返回对象（E1）+ `build_confirmed_scope` 快照扩键（E2，additive 读容忍）+ `mark_compiled`/`supersede_plan` 双态写者（E3，idem 盐 = 旧 plan id 哈希输入，无 revision_of 指针字段）+ `route_revision` 修订路由器纯函数（R20：plan_ref/output_id → 快照/地图存在性检查 → 任务切片 → 全链 fill_key 投影 → by_fill_key 节点匹配，partial match 诚实降级，legacy 无键降级）。Start 座已接线（快照带 map +同事务 mark_compiled）。纯 pytest 546 绿 + check_gates OK
- **基线**：纯 pytest 基线 507 → S1 后 546；prompt_gate 4 探针（A/B/C/D，阈值 8/8/10/8）

## 4. S2 当前状态：施工中、**未提交**（接续点）

### 4.1 已落并实测（编译 OK + 纯 pytest 546 绿）

改动文件（`git status` 可见，全部未提交）：

1. **新模块 `apps/api/app/chat/exploration_compile.py`**：两条 turn path 的**共享编译座**（R12/R14 双门一条法律一个座位，消除镜像漂移）——`PlanPreview`（pre-flight 替身，从 plan_turn.py 搬来）、`CompiledPackage`（journey_id/selects/candidate_sets/plans/tasks/plan_task_map）、`compile_plans_package()`（journey 解析「one call plans one journey」→ preview 编译 → transform 护栏 → 门出生 → map re-key 到真行）、`recompile_journey_package()`（revise 的整包重编译，真行直编）。返回 `CompiledPackage | str`，str = loop echo 原文（错误文案是回声合同，措辞勿动）
2. **`exploration_tools.py`**：`ProposePlansArgs`/`RevisePlanArgs` 增 `pending_disposition: Literal["answer","skip","none"]="none"`（chat path 信封座；plan path 永不读它——PlanTurn.execute 不读 disposition）；`exploration_chat_tools()` docstring 改为双路投影
3. **`plan_turn.py`**：`_propose_plans`/`_revise_plan` 机械换基到共享座（行为保持：同样顺序、同样错误串、同样 dock 下文）；`_PlanPreview` 删除；imports 清理（dataclass/GraphNode 移除，exploration_store/scope_compile 收窄）
4. **`propose_turn.py`**（ChatTurn）：`on_activity` 通道入 `__init__`；`execute` 在 disposition 前言后 dispatch `EXPLORATION_TOOLS`；新座位 `_emit_milestone`/`_resolve_persona`（project.persona_id → resolve_default_persona，plan path 链减 request/stored）/`_explore`（candidates/selects 非终态 ToolObservation + 里程碑；project=None 诚实边界）/`_propose_plans`/`_revise_plan`（终态，走本路 dock 座）；`_dock_plan_as_question` 扩 additive kwargs（plans/plan_task_map/derived/persona_id——router-drafted 调用方 propose_tasks/edit_graph 一律不传，保持 pre-S2 形状）；`run_propose_turn` 增 `on_activity`；模块 docstring 增 S2 段
5. **`service.py`**：`_propose_turn` shim + 两个调用点（execute_chat_turn chat 分支 + answer_question 续轮）穿 `on_activity`
6. **`intent.py`**：`chat_intent_agent` tools 增 `exploration_chat_tools()`；`max_iterations` 6→12（E8，注释带 2026-09-23 S-explore-2 实测依据：现实链 8-10 调用 + 2 恢复余量）；模块 docstring 更新

### 4.2 关键设计拍板（已锁定，勿重开）

- 探索 dock **必须**带 `plans` + `plan_task_map`——否则 Start 的 mark_compiled/快照在 chat 路 dock 上失效（E3 状态机断）
- `_dock_plan_as_question` 是 chat 路**唯一** dock 座，扩件全 additive；propose_tasks 的 `derived=[]` 现状是既有形态，**本批不动**
- chat 路 dock 无 active-run 护栏是**本路既有姿态**（Start 出生地护栏兜底），探索 dock 照旧——勿补
- bail 清 `project.pending_brief=None`（service.py:1500）→ chat 路 revise 座重新解析 persona
- 探索 dock 算 `derive_plan_preview`（三面诚实）；propose_tasks 不算（既有，出本批范围）
- 里程碑键 `chat.explore.candidatesReady/selectsReady/plansReady` 已在 activity.py + web i18n 注册，直接复用

### 4.3 S2 剩余清单（按序做完才算 S2 完）

1. **`apps/api/app/prompts/chat/chat_intent_system.j2` 增发现型判定段**（合同 §4 S2 原文要求：R6 parity——post-run「再挑两条」= 新 journey 探索链；修订话术 → 修订动词；「更智能 = 事事探索」永禁照抄）：
   - 头部 provenance 注释加一行（iter-3 S2, ADR-088 R6 chat parity, 2026-09-23）
   - 顶部终态工具清单增 propose_plans / revise_plan 两条紧凑 bullet
   - SPEECH 段增两者的言语职责（镜像 intent_router_system.j2:37/48 的紧凑版：propose_plans = 决策包引介 1-3 句——找到了什么一句话/方案做什么/唯一下一步；name 参数命名作品；禁复述区间/候选数/工具名；revise_plan = 一句确认改了什么）
   - 新增 DISCOVERY GOALS 小节（post-run 改编版）：正形态（'再挑两条关于定价的'/'what else does my talk say about X — make posts'）→ 一轮跑完四步链（search_transcript 静默读 → get_segment 逐字读 → propose_candidates（goal 命名目标开新 journey）→ propose_selects → propose_plans TERMINAL）；**反形态留在既有短路径**（加字幕/配音/新语言版 → propose_tasks；改已有产物 → edit_graph/apply_edit_ops；参数明确的干脆请求永不绕探索链）；边界句：修订话术永远走修订动词不走发现；无素材无可搜（material 门照旧）
   - 参考镜像源：`intent_router_system.j2:53-58`（plan 路 DISCOVERY GOALS），改编点 = post-run 语境 + 反形态指向 edit_graph/apply_edit_ops
2. **`apps/api/app/chat/context.py` Graph 段探索行标签**（认知验收「agent 看见了什么」）：探索节点当前渲染 `- exploration id=X state=ready — exploration`（spec 无 summary 键，label 退化成类型名）。改为：仅当 `n.type == "exploration"` 时 `label = spec.get("title") or spec.get("topic") or spec.get("exploration_kind") or n.type`；执行节点行一律不动。cap 16 律不动
3. **纯测试 `apps/api/tests/test_exploration_compile_pure.py`**（新文件，复用 test_exploration_store_pure.py 的 `_StubDb` 模式——GraphNode/Journey/Asset 列表服务，JSON-path 不求值；seed 要精确）：
   - journey 解析：未知 select → 错误串；跨 journey → 错误串；单行通过
   - `compile_plans_package`：preview id 命名 `preview:{select_id}`、draft/ready 状态门（plan_completeness_issues）、出生顺序 zip re-key 到真行 id、门拒绝 → echo 串零写
   - `recompile_journey_package`：真行直编、map 键 = 真行 id
   - 编译面用简单链（writer-only 或 clips-only——check_transform_targets 对无 translate/dub 链平凡通过；project_source_language 读 asset meta.language，stub 供 Asset）
   - `pending_disposition` 字段在 ProposePlansArgs/RevisePlanArgs 上的默认/合法值/非法值
   - 注意：测试里 `current_ui_language()` 无请求上下文 → None → default_language 回落 "en"，可预期
4. **prompt_gate 全量复跑 + 新探针 E**（`apps/api/scripts/prompt_gate.py`）：
   - 探针 E = post-run 发现型：chat-path 形态 agent（`system=chat_intent_system()`、`assemble=_assemble_chat_turn`、`tools=[*CHAT_TOOLS, *CHAT_READ_TOOLS, *exploration_chat_tools()]`、`max_iterations=12`、client 同 PROVIDERS）；context 用 `_assemble_chat_turn` 的 `{"text": ...}` 形态手工拼（Project 行 + Assets 一段含可读 video + Current outputs 一行 + Latest run completed + message='再找两段我讲到 onboarding 的地方，剪成短片' 类发现型话术）
   - 通过谓词建议：`r.tool_name == "propose_plans" and "propose_candidates" in r.calls and "propose_tasks" not in r.calls and "edit_graph" not in r.calls`
   - stub execute 复用 `_gate_execute`（感知 + 探索动词已_stub 好）；main() 里按 probe 选 agent 形态
   - **纪律：先跑 12 发看带再封阈值**；`THRESHOLDS["E"]` 起步保守（参考 D=8），注释记实测带；失败 = 复跑一次再二分，**永不调阈值让回归过**
   - 全量四探针（A/B/C/D）也必须复跑全绿——prompt 面改动必跑
5. **提交 S2**：一个 commit，`feat(iter-3): S2 chat path 产品语义化——探索族入 chat_intent + 共享编译座 exploration_compile + 发现型判定段 + loop 预算 12`（附 attribution 行）；简报 Status 行 S2 标 ✅ 带 SHA
6. **check_gates**：`uv run python scripts/check_gates.py`（S2 触碰注册表面，跑完确认）

## 5. 冻结条速记（全文 = 母合同 §1，违即停问）

1. 停顿定律：每个付费范围授权边界停一次；范围内续作零仪式；扩范围才重确认
2. 决策包可编辑律：未确认包原地更新重报价同一确认座；「确认失效→再弹一次」永禁
3. Reviewer 边界：确定性兑现审计 + 建议；主观质量词零字；自治修 P2 不在主线；reviewer 永不自宣续作
4. Memory 三不：三需求永不合并；零新 memory/goal 域对象；agent 无静默升格写路
5. select_clips 零代码（S0 只落裁决文档——已落）
6. 执行世界零改动七件：apply_wiring_ops / create_run / Start 四合取 / hold→capture→release / fencing / workflow_steps；R19 接线 = **消费** classifier 裁决不是改裁判
7. 迭代二 §5 避让全部继承
8. 新词先入 NAMING；i18n en 先 zh 镜像；展示文案二源律；凭据/.env 纪律；stash 唯一 tag

## 6. 验证纪律（每 commit 自绿 + 批次收口）

- 每 commit：`uv run python -m compileall app -q` + 相关纯 pytest 全绿
- prompt 面改动（S2/S3/S5/S6）必跑 prompt_gate；失败 = 复跑一次再二分，永不调阈值
- 纯测试例外条款：只覆盖裁决/纯映射层（无 DB 无 LLM 无 HTTP）；需要真事务/LLM 的行为归 e2e 剧本
- fixture 纪律：scenario/ 前缀、真实 words、禁共享 demo key
- 认知验收三问进每片 DoD：agent 看见了什么 / 内部表示是否一致 / 怎么知道自己对了
- 没跑的验证诚实标「未跑验证」
- IDE 的 Pyright 诊断（3.10 union 语法 / pydantic/sqlalchemy 不可解析）是 IDE 环境误配噪音，未改文件也报——**忽略，以 `uv run` 实测为准**

## 7. S2 之后：S3~S9 概要（全文在母合同 §4，按依赖序施工 S3→S4→S5→S6→S7→S8→S9）

- **S3 revise_output + R19 接线**（依赖 S1✅+S2）：chat path 终态工具 args=`{target:{plan_ref?, output_id?}, instruction}`（E4）；R20 路由器消费；ops 代码组装 edit_prompt+run（prompt 消费族门控）；classifier 裁决消费（`_edit_graph` 机械全件复用：savepoint / GraphDelta / tasks_for_graph_nodes / continuation 自治跑 / expansion·unproven 回滚转迷你 dock）；迷你决策包 = 既有 `_dock_plan_as_question` 座（S2 已扩件）；诚实降级三态（无快照/legacy → 散文 + @output 兜底反问；目标全是确定族 → 「能改的是…」；部分可改 → 部分执行 + 散文说明）；review 注记④：`resolve_source_span_texts(asset_id=None)` 回退**原样保留**并在简报销记（本路径指认恒钉 id）；纯测试 + prompt_gate + 决策包修订探针（12 发看带）
- **S4 选择修订三金钱态**：写门 `revise_selects` 分支（member_index 编辑 + bounds 重校验 + idem 保留 + state→revised）+ 双路注册 + dock 前零仪式/dock 后原地更新同确认座/run 后 supersede 迷你包；剧本座 S-explore-4
- **S5 收官兑现审计**：`app/pipeline/run_review.py` 纯核（类型/语言/时长 vs 裁切区间/字幕轨/配音存在/outputs.quality/实扣 vs 报价，零 LLM）+ trigger 回合 context 注入 + `trigger_system.j2` run_completed 改写（先事实、主观零字、缺口出建议走既有编号选项问）；剧本座 S-explore-5；**自治修不做（P2）**
- **S6 Memory 三需求窄切**：`get_artifact` read 注册 perception（ADR-088 §7 洞销账）+ `build_context` 历史 journey 有界摘要行（cap 3 新先）+ exemplar 事实行注入（E5，无代码侧参数映射）；R25 按 E6 **砍 = 零代码**
- **S7 过程可见升级**（web 为主）：wire 增 `at`/`duration_ms`（E7 additive）+ web 镜像类型 + NAMING 注记；共享时刻排序层（messages.at × activity.at 单流穿插）；ActivityStream 固定底块退役入流；ActivityRow 耗时 + 有界展开；vitest+tsc；i18n en 先 zh 镜像
- **S8 迁移弧执行**（依赖 S2/S3/S4）：edit_graph 退役证明（旅程三承接面对账表 + 全量剧本绿 + grep 零生产调用）→ 达标即退役（CHAT_TOOLS 除名 + dispatch 删除 + prompt 清理 + S4 剧本本质迁 S-explore-3）；不达标留档零删；ADR-088/089 注记现在时改写
- **S9 六拍终态验收**：S-explore-3/4/5 三座常驻全绿（确定性尾先行 + LLM 拍位串行复跑）+ 全量门禁 + 受影响旧剧本（S-explore-2/S23/S4/S7/S13/S16/S19/S22 串行 live 复跑）+ **六拍 live 走查证据脚本 `scratch/iter3-six-beat-walkthrough.md`（由用户真人跑，你交付脚本与检查表）** + docs 收口（PROGRESS §0.2 / JOURNEYS 拍 3/4/5/6/8/9/10 / MODULE_ARCH §7 登记 run_review+router 座 / verification-contracts.md 登记三新剧本 / 简报归 `archive/tasks-done/`）

## 8. iter-2 review 遗留注记（勿踩）

- ③ `RevisePlanArgs.instruction` 不消费 = **设计如此，勿修**
- ④ `resolve_source_span_texts(asset_id=None)` 回退 = S3 简报销记即可，勿动

## 9. 开工第一动作

```bash
cd /Users/sylas/repurposer/.claude/worktrees/iter2-cut-segments
git log --oneline -3 && git status --short
```

确认 HEAD = `bf4d771`、S2 未提交改动在场（§4.1 文件清单），然后读完全部必读（§2），从 §4.3 第 1 项继续。上下文/预算将尽时：停在切片边界，把简报 Status 行更新为当前进度（本文件 §4 的写法就是模板），不赶工跨片半吊子。
