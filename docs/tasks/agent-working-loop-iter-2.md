# Agent Working Loop 迭代二：能力编译层 + 决策包/快照 + R6 路由——主链 e2e 首通

> Status: **已落地并实测全绿（2026-09-23）**——①~⑦ + §4.1 编译器 + §4.9 S-explore-2 全部落地（branch `feat/cut-segments`）；LLM 驱动面同日实测销账：prompt_gate 全量四探针 48/48 PASS（A/B/C/D 各 12/12）+ S-explore-2 live e2e 全链绿（7 迭代净发现环 → 决策包 dock → confirmed_scope 五字段 → run completed，clip+post 落地）。实测猎得三修真修同批落地（`5c9ac44`：asset_id 观察头接力 + 供方 `{"item":...}` 数组方言线级拆包 + loop 预算 8→12）。拍板项见 §3。
> 母合同 = ADR-089（§1 编译移出 LLM / §2 编译合同 / §3 编译器座位 / §4 决策包与快照 / §5 停顿定律 / §6 修订分类 / §7 报价站 artifact 事实 / §8 迁移弧）+ ADR-088 §9（R6 发现型路由）+ JOURNEYS 旅程四拍 0、6、7。迭代一（`archive/tasks-done/agent-working-loop-iter-1.md`）已落地承重：探索三族 + 写门 + 证据 reads + EXPLORATION_TOOLS（harness 级）+ 画布三卡面 + S23。

## 1. 三次迭代切分（承接，用户拍板 2026-09-22）

| 迭代 | 内容 | 状态 |
|---|---|---|
| 一 | 探索产物族数据面 + 画布呈现 + S23 剧本 | ✅ 已落地并实测全绿（S23 LLM 三拍 2026-09-23 复跑 PASS，挂账销） |
| **二（本批）** | 编译器（Content Plan → Execution Scope）+ 决策包 + Confirmed Scope Snapshot（销 P0-①）+ R6 发现型路由（EXPLORATION_TOOLS 生产接线）+ work session 活动视图 + R15 停顿 + revise_plan（重编译→重报价→重确认）→ **主链 e2e 首次全通** | ✅ 已落地并实测全绿（2026-09-23；prompt_gate 48/48 + S-explore-2 live e2e） |
| 三 | revise_output + R19 两分律接线 + R20 快照修订路由器 + reviewer 合同 + 记忆读取律 + 迁移弧收口 + 活动行呈现升级 + 终态对标验收 | 后续 |

## 2. 开工裁决承接（迭代一复述，本批承重）

- **select_clips**：保留为执行工具（零探索退化形态唯一机制）；**编译器永不从 Content Plan 编译出 select_clips**（发现语义已上移到 chat 边缘，执行世界不许再有第二个发现者）；退役评审 = 迭代三迁移弧。
- **迁移弧纪律**：`propose_tasks` / `edit_graph` 与探索流**并行 → 证明 → 退役**，一刀切永禁。本批 = 并行期开始：探索链生产接线，既有 chat 路原样承重零改动。
- **既有合同零改动**（ADR-089 Consequences 重申）：`apply_wiring_ops` / `create_run` / scope classifier / Start 四合取 / hold→capture→release / fencing / dock pill 唯一座 / 确认教义 / 打字机律 / Activity 十规则——本批只改「谁有资格向执行世界递东西」。

## 3. 拍板项（全部带推荐答案；无新议题 = 直接开工）

**① clip 编译目标 = 新确定性工具 `cut_segments`**（已拍板施工，2026-09-23 落地）。
证据：iter-1 裁决禁编译 select_clips；registry 现存确定性工具（reframe/dub/translate/music/filler）全部以既有 clip 为输入，无「从区间产出首个 clip」的座位。**产品先行的最终形态**（施工前再裁决，推翻首版参数面）：params = `segments: [{start, end}]`（1..5）+ `asset_id?`（Select 唯一源编译期显化）+ `aspect?`（出生属性，用户可点名）——**caption_mode / language 不进出生参数**（语言版本/字幕形态/配音全是 transform 语义，各有能力续链：translate_clip / dub_clip；源语言字幕是出生的唯一诚实形态）。runner = `materialize_source` 零 LLM 配置一般化到 N 区间（共享 resolve_render_source / build_clip_spec / 渲染扇出机械）。同批并入：**PlanOutput 产品语义三缺口补齐**（+aspect 词表、+dub 布尔、caption_mode 收窄三值词表——安全窗口 = R6 生产接线前无生产 plan 行）+ 卡面展示。结构性要求落地为**注册表新轴 `llm_visible`**（N-56）：注册表合法但永不出现在 Agent 工具目录（compiler-only 公民）；N-32 一类型一生产者法相应收窄到提案空间。NAMING N-56 已登记。

**② writer 源域收窄 = 四 writer 共享 `CopyWriterParams` 增可选 `source_span`**（推荐）。
plan-sourced 写作的对象 = Select 的证据段不是全篇。`source_span: {start, end} | null`（null = 现状全篇——零探索退化形态与既有 chat 路不变）；step_context 注入点一处：有 span 时 writer 的素材上下文 = 该段 transcript（`words_in_range` 同函数，与门/读面同一法律）+ 理解摘要照旧。plan 的 per-output `brief` → `focus` 映射（既有字段，语义全等）。

**③ 决策包 = task_book dock 载荷升级，不是新 dock 种类**（推荐）。
确认面消费三层（ADR-089 §4）：**阅读层** = Content Plans（LLM 命名的方案语义——展示文案二源律）+ **证据层** = 编译产物 TaskItem[]（可展开，user-safe）+ **费用语义五面**（ADR-087 §2.1 不动）。`question.kind="task_book"` 存储字冻结不动（N-52）——payload 增键不更名；dock pill 唯一座（ADR-070）不变；不可编译的方案永不进 dock（B3「只有注册表合法的链才进 dock」上移——编译失败 = 域拒绝回环修复，LLM 修 plan 重来）。

**④ Confirmed Scope Snapshot 住 `run.context.confirmed_scope`**（推荐）。
Start 手势落戳（销 P0-①）：`{confirmation_id（= 确认消息 id）, confirmed_at, confirmed_via: "dock_pill" | "chat_reply", plans: [...], compiled_scope: TaskItem[], quote: {low, high}}`。legacy run = 不可证（与 D2 读法一致）；R20 修订路由器 = 迭代三，本批只写不读。

**⑤ R6 路由 = plan path 发现型判定 + EXPLORATION_TOOLS 生产注册**（推荐）。
`intent_router_system.j2` 增判定段：发现型目标（「找最好/挑/哪些」语义，实现空间未定）→ 探索链（reads → propose_candidates → …）；干脆请求照旧 present_plan 短路径（**「更智能 = 事事探索」永禁**）。工具集：`PLAN_TOOLS + EXPLORATION_TOOLS + PLAN_READ_TOOLS`（reads 已注册，迭代一）。prompt_gate 加**探针 D：发现型目标 → 终态必须是 propose_candidates 而非 present_plan**（阈值随批实测定，先跑 12 发看带再封线）。

**⑥ work session 活动视图 = 四个活动键，user-safe 只带计数**（推荐）。
`chat.explore.searching` / `chat.explore.candidatesReady`（N 段）/ `chat.explore.selectsReady`（N 个）/ `chat.explore.plansReady`（N 方案 · ready/draft）——Activity 十规则全守（白名单键、i18n 双写、永不带 params/raw results/reasoning）；穿插呈现 = in-session（JOURNEYS 注记 6），本批不做活动流持久化。

**⑦ revise_plan = 恒重确认，R19 自治判权归迭代三**（推荐）。
终态工具 `revise_plan`（args = plan 指认 + 修订散文）→ 探索写门修订路径（plan 行 state → revised，新 spec）→ 重编译 → 重报价 → 重 dock。scope classifier 的 continuation/expansion 判权**不在本批**（R19 接线 = 迭代三 ⑥）；本批一切 plan 级修订一律重确认（R15 停顿定律的最保守读法，零自治风险）。

## 4. 施工内容

### 4.1 编译器（ADR-089 §2/§3，`app/pipeline/scope_compile.py` 新文件）
- 纯函数 `compile_plans(plans × selects × candidate_sets × goal × registry) → TaskItem[]`：
  - 每 plan：select → candidate member 区间（R7 指针**编译期**解算，探索行只读）；
  - `clip` 输出 → `cut_segments`（区间直入；`language` ≠ 源语言 → 续 `dub_clip` / `translate_clip`，与既有链同法）；
  - `post` / `article` / `quotes` / `carousel` → 对应 writer（`language` + `focus=brief` + `source_span`）；
  - 编译失败（区间缺失 / kind 不可映射 / 注册表不收）= `ScopeCompileRejected`（域拒绝，回环修复座位）。
- 编译器座位（R14 编译器半边）：自身零写特权——产物经既有路径落（dock 载荷 / create_run 消费同一 TaskItem[]）。
- 估价（§7）：quote = 既有 fold 机制作用于编译产物（区间时长 → 渲染单位——输入站 plan 事实，不站 LLM 提议）。**现状诚实注记（① 落地后）**：`cut_segments.estimate` = 全零（机械装配无计价单位，materialize 先例）；渲染扇出 = 运行中出生（P4 NULL）；「语言数 → dub 单位」超出现行估价机械（dub/translate 对未出生 clip 的报价恒 NULL）——编译期总价面 = 决策包（拍板项③）的待解话题，不在 ①。

### 4.2 `cut_segments` 工具包（`app/tools/clips/` 同包，注册表新条目）—— ✅ 已落地（2026-09-23）
- params: `segments: [{start, end}]`（1..5，`extra=forbid` 严格编译器契约）+ `asset_id?` + `aspect?`——**无 caption_mode / language**（transform 语义各有能力，出生只产源语言字幕形态）；
- runner = `materialize_source` 零 LLM 模板一般化（**不是**「复用 select_clips」——select_clips 的发现/清项目/评分三段一概不继承）；`needs_media_file=True`、`behavior="deterministic"`、`llm_visible=False`（N-56 公民轴首座）；
- 摘要模板双语（「裁出 N 段 · 共 S 秒」）；NAMING N-56 已登记；**prompt 面零扰动**（llm_visible=False 使目录投影与 no-material 枚举字节不变——一致性测试投影收窄护航，prompt_gate 无新针）；
- 编译路径四处窄集成（output_type 声明化 producer 判定 ×2 / label 座位 node_cls 直读 / spec 原样携带 + prelude-free 出生）+ N-32 收窄 + node_for_output 硬化 + morph/lifecycle 谓词声明化 + 5 个 after 元组——全部恒等守护既有链（纯测试 17 例 + 全量 452 绿 + 启动自检过）。

### 4.3 writer `source_span`（`derivative_dispatch.CopyWriterParams` + step_context 注入点）
- 字段增列（null = 现状）；step_context 有 span 时素材上下文 = 段内 transcript + 理解摘要；
- 既有路径零行为变化（零假设测试：无 span 的 prompt 装配逐字节不变）。

### 4.4 决策包（dock 载荷升级 + 编译回环）
- plan path 终态：`propose_plans` 落写门后 → 编译（4.1）→ 成功则 dock 决策包（plans + tasks + 五面）；失败 = echo 回环（LLM 修 plan 重提）；
- dock payload：`plans: [{plan_id, title, outputs, state}]` + `tasks: TaskItem[]` + `quote` + 既有 task_book 键全保留（旧行回放读容忍不变）；
- 前端 dock：task_book 卡增「方案阅读层」段（plans 在上、tasks 证据可展开——卡面文案 i18n 双写）。

### 4.5 Confirmed Scope Snapshot（销 P0-①）
- Start 落点（plan path `start_run` 执行座）：写 `run.context.confirmed_scope`（形状见拍板项④）；
- 纯测试锁形状 + 剧本断言；legacy 读容忍（无快照的 run 一切照旧）。

### 4.6 R6 路由 + EXPLORATION_TOOLS 生产接线
- `intent_router_system.j2` 判定段（发现型 vs 干脆，各带正反例）；`PLAN_TOOLS` 注册三动词；
- execute 派发：plan_turn 增探索动词座位（调 `execute_exploration_tool`，拒绝 echo 回环）；
- prompt_gate 探针 D 上线（拍板项⑤）；既有 A/B/C 阈值不动、必过。

### 4.7 work session 活动键（拍板项⑥）
- 四键注册 + i18n 双写；plan_turn 在门调用成功处发活动事件（in-session 穿插，不持久化）。

### 4.8 revise_plan 终态工具
- args: `plan_id`（@output 指认或观察面 id）+ `instruction`（修订散文）+ 修订后 outputs（LLM 全量重述——读容忍）；
- 写门修订路径：原 plan 行 `state → revised`、spec 更新（`revision_of` 不建——同一行修订，无版本树）；issues 重检 → draft/ready；
- 重编译 → 重 dock；旧 dock 计划 supersede（既有机制）。

### 4.9 S-explore-2 剧本（主链 e2e 首通）
- 生产 chat 全链：发现型目标（SSE）→ 探索三族出生 → 决策包 dock（plans+tasks+quote 断言）→ 确认 → run 启动（confirmed_scope 断言）→ 产物落地；
- fixture 纪律同 S23（scenario/ 前缀、真实 words）；MiniMax 配额是硬前提——**已实测（2026-09-23）：live e2e 全链绿**。

## 5. 避让清单（撞一条 = 停手问）

- 执行世界零改动：`apply_wiring_ops` / `create_run` / scope classifier / Start 四合取 / hold→capture→release / fencing / workflow_steps。**偏差记录（①，2026-09-23）**：`compile_graph` / orchestrator 与 morph/lifecycle 谓词发生了**窄集成**——「链上有 clips 生产者」判定从 `select_clips` 名检改为 `output_type=="clips"` 声明读法（不改则 cut 链会误注 materialize_source / 同语言裁决漏判）、label 座位改 node_cls 直读（不改则 cut 步骤被 select_clips 冒名）、spec 携带与 prelude-free inputs、N-32 自检收窄 + node_for_output 硬化、5 个 morph `after` 元组补位。全部经恒等性纯测试守护（既有链拓扑/标签逐字节不变），属「谁有资格向执行世界递东西」的最小扩面，不触执行语义。
- `propose_tasks` / `edit_graph` / chat 路既有行为零改动（迁移弧并行期——两条路并行证明，谁也不动谁）。
- 确认教义 / dock pill 唯一座 / G-1 / trigger turn 白名单 / 打字机律（新增散文字段带读容忍）/ Activity 十规则 / R18 同框纪律。
- 探索写门内部件零改动（迭代一已绿）；本批只在门**外侧**消费（编译期读探索行 = 只读）。
- 编译器永不编译 select_clips；`cut_segments` 永不带发现语义（无 focus/count 参数）。
- reasoning / CoT 永不持久化；决策包 evidence 层 user-safe（无 raw params 进阅读层）。
- 词表纪律：新词先登记 NAMING（`cut_segments` / `source_span` / `confirmed_scope` / 活动键）再进代码。
- i18n en 先 zh 镜像；展示文案二源律（plan 名 = LLM 命名 / 事实 = 世界自证；冻参模板永禁）。

## 6. 验证纪律

- 会话内自跑：compileall、纯 pytest 全量（编译器纯函数全谱 / snapshot 形状 / 决策包装配 / revise 写门路径）、check_gates、prompt_gate（A/B/C 旧三针 + 新 D 针）、web tsc + vitest。
- 零假设测试：writer 无 span 装配逐字节不变；旧 task_book dock 行回放读容忍。
- S-explore-2 需 dev API + worker + MiniMax 配额——**已实测（2026-09-23）**：全链 PASS（7 迭代净发现环；实测修复三件套随批，见 Status 行）。
- 认知验收（PROGRESS §0.4 规则 9）DoD 三答：agent 看见什么（决策包三层 + reads）/ 表示一致吗（plan ↔ tasks ↔ quote 同源编译）/ 怎么知道对了（编译拒绝回环 + 快照可证 + 剧本断言）。

## 7. 验收标准

1. 编译器纯测试绿：三族输出映射全谱（clip±语言版 / 四 writer / 区间解算 / 拒绝回环）；永不出现 select_clips。
2. 决策包 dock：阅读层（plans）+ 证据层（tasks）+ 五面费用语义同卡；不可编译方案永不进 dock。
3. Start 落戳：`run.context.confirmed_scope` 五字段齐（confirmation_id / confirmed_at / confirmed_via / plans / compiled_scope+quote）；legacy run 读容忍。
4. R6 路由：prompt_gate 四针全过（D = 发现型 → propose_candidates 终态；A/B/C 无回归）；干脆请求照旧短路径。
5. work session 四活动键在 SSE 活动流可见（user-safe，只带计数）。
6. revise_plan：修订 → 重编译 → 重报价 → 重 dock 全通；原 plan 行 state=revised。
7. S-explore-2 主链 e2e 绿（**已兑现 2026-09-23 live**）。
8. 零改动清单实证：执行世界七件 + propose_tasks/edit_graph 行为面 diff 为零。

## 8. 收口

- PROGRESS §0.2 本批行；NAMING 新词登记；MODULE_ARCH §4 无新表（快照住 run.context）但编译器座位入 §7 代码地图；JOURNEYS 拍 0/6/7 状态翻新。
- conventional commits，每 commit 自绿；报告 = 改动文件 / 测试 / 剩余风险 + 迁移弧进度复述。
