# Agent Working Loop 迭代一：探索产物族数据面 + 画布呈现

> Status: **施工中（2026-09-22 开工，三次迭代之第一次）**
> 母合同 = ADR-088（§1~§5 探索产物族 / 双状态机 / 居住律 / 探索写门 / 免费区连续）+ JOURNEYS 旅程四拍 0~5a；命名 = NAMING N-55（prototype 第四值 `exploration`）；北极星与验收口径 = PROGRESS §0.1「终态体感对标 OriginCut 左栏」（本批不对标终态，只交地基 + 呈现，终态验收在迭代三）。

## 三次迭代切分（用户拍板 2026-09-22：一大批做三次）

| 迭代 | 内容 | 旅程四拍位 |
|---|---|---|
| **一（本批）** | 探索产物族 schema + 探索写门 + 证据 reads + 探索终态工具族（harness 级，不接生产 chat agent）+ 画布探索族卡面 + I-EXPLORE-01 守卫 + 剧本 | 拍 2~5a 的对象与呈现 |
| 二 | 编译器（Content Plan → Execution Scope）+ 决策包 + Confirmed Scope Snapshot（销 P0-①）+ R6 发现型路由（生产接线）+ work session 活动视图 + R15 停顿 + revise_plan（重编译→重报价→重确认）→ **主链 e2e 首次全通** | 拍 0、6、7 |
| 三 | revise_output + R19 两分律接线 + R20 快照修订路由器 + reviewer 合同 + 记忆读取律（Tier 1 + 历史旅程摘要 + R25）+ 迁移弧（propose_tasks/edit_graph 并行→证明→退役）+ 活动行呈现升级（横切 6）+ **终态对标验收（六拍剧本）** | 拍 8、9、10 |

## 开工裁决：select_clips 存留（ADR-089 §8 ADR-PENDING 第一件事）

- 探索链来源工作：发现已移至 chat 边缘（search_transcript → propose_candidates → propose_selects），Content Plan 携带具体区间 → 编译产物 = **确定性裁剪**，编译器（迭代二）**永不从 Content Plan 编译出 select_clips 节点**。
- 干脆请求（零探索退化形态）：执行时 LLM-select 仍是唯一机制 → `select_clips` **保留为执行工具**，本批零代码改动。
- 迭代三迁移弧收口时再评退役：若干脆请求届时全走退化编译、执行时 LLM-select 失去最后调用方，才退役；长素材二次裁切 / 语义连续处理若实证需要，以 execution-time transformation 身份保留。

## 施工内容

### 1. Schema（alembic migration）
- `journeys` 新表：id / project_id（CASCADE）/ goal_text / created_at / updated_at——journey_id 的诚实出处（R24 归属属性，永不成图边）。
- `graph_nodes.journey_id` 新列（nullable + index）：探索产物携带；执行节点为 NULL。
- MODULE_ARCH 表归属登记 + DATABASE_MIGRATIONS 流程（版本文件入库提交）。

### 2. 探索产物 spec 形状（schemas.py，pydantic 校验 spec JSONB）
- `spec.prototype = "exploration"`（NAMING N-55 第四值）+ `spec.exploration_kind ∈ candidate_set | select | content_plan`；`type` 取词决策实施时按画布卡面分发实测定（候选：单族词 `exploration`，词表 v3 加 NAMING 注记）。
- **CandidateSet**：`{asset_id, topic, members: [{start, end, excerpt, speaker?}]}`——R1 合集律（一个 artifact，默认折叠可展开），每字段可回溯 transcript。
- **Select**：`{candidate_set_id, member_index, verdict, reason}`——R7 证据引用（不复制源）；R3 理由 = 属性（verdict + 一行用户安全结论），reasoning 永不持久化。
- **ContentPlan**：`{select_id, title?, outputs: [{kind, language?, caption_mode?, brief?}], persona_id?}`——R8 ≠ Task（产品语义：source range 经 select 引用 / 产出要求 / 语言 / 字幕 / 文案 / persona 引用）；R9 persona 在 Structure 注入。
- 完整性自检（拍 5a）：确定性纯函数（区间 / 语言 / 产出类型 / 必填输入）→ artifact state `draft → ready`；**探索族状态机 = draft → ready → revised → compiled → superseded**（ADR-088 §3，本批只用 draft/ready/superseded，compiled/revised 随迭代二三）。

### 3. 探索写门（`app/pipeline/exploration_store.py`，MODULE_ARCH 登记）
- **R14 双门**：探索写门 ≠ 执行写门（`apply_wiring_ops` 不动）；两套不变量——探索门：免费但真写门（savepoint 事务 + 证据校验 + 回合幂等）；**探索节点永不带边**（写门拒绝为 exploration 节点建边）；执行门反向守卫：`apply_wiring_ops` 拒收 prototype=exploration 节点（执行写门只写执行族）。
- 证据校验：`start < end`、`end ≤ asset.duration_seconds`、excerpt 与 transcript 有交集（确定性比对）。
- 回合幂等：同 turn 同工具同参数重放 = 返回既有 artifact（键 = journey + kind + 参数哈希）。
- 三个写操作：`propose_candidates`（无 journey 则 mint）/ `propose_selects` / `propose_plans`（含完整性自检落 ready）。
- 纯核 + 装配器形态（scope_classifier / lifecycle 先例），零 LLM、零 HTTP。

### 4. I-EXPLORE-01 守卫 + 纯测试锁
- 执行闭包（下游遍历 / run 填充）、quote/rank、媒体流边语义对 exploration 节点**结构性盲**——守卫优先坐纯函数层（facts 只统计执行族），坐不了纯函数的坐写门拒绝。
- 前端镜像：ResultsCanvas 价格 fold（prototype generator/editor 才计价）天然排除；FlowNodeCard 程序区门控同理——断言传进纯测试/断言层，不靠巧合。

### 5. 证据 reads（perception 注册，生产可用）
- `search_transcript`（确定性关键词检索 read：params = query + asset_id?；返回命中段 start/end/excerpt/speaker，有上限 + 诚实省略注）与 `get_segment`（params = asset_id + start + end；返回该区间全文）。
- 同修复批注册全形（name + params schema + execute + activity_key + en/zh 双写）；**prompt 面改动 → prompt_gate 必过**。
- 转写段来源：`Asset.transcript` + `Asset.meta`（ASR 词级时间戳）——无词级时间戳的素材诚实降级（返回「此素材无时间轴」而非编造区间）。

### 6. 探索终态工具族（harness 级，**不接生产 chat agent**）
- `propose_candidates` / `propose_selects` / `propose_plans` 的 args schema + executes（终态 = 经探索写门写图 + 回 observation 摘要）。
- 独立 `EXPLORATION_TOOLS` 注册表，**本批不进 turn_tools.py 生产工具集**（生产接线 = 迭代二 R6 同批，防注册表扰动半接线的词表）——剧本 harness 自行组合工具集驱动（prompt_gate 组 PLAN_TOOLS 先例）。
- 迁移弧纪律（ADR-089 §8）：propose_tasks / edit_graph 本批零改动，并行期从迭代二开始。

### 7. 画布探索族卡面（前端）
- 三种卡面：**候选集合集卡**（默认折叠 = 一行摘要「14 个候选」；展开 = 成员列表：区间 + 一句话摘录）、**精选卡**（区间 + verdict + 一行理由）、**方案卡**（draft 虚线 = ADR-057 K5 既有草稿形态；产出要求清单 + state 徽 ready/draft）。
- R18 同框纪律：探索族永不镜像 running（状态语义不共享）；无端口、无边（I-EXPLORE-01 前端投影）。
- layout.ts：探索族出生帧分配（append-only 纪律不破；简单车道规则，画布组织学 P2 挂账不做）。
- graph API（`GET /projects/{id}/graph`）直读持久图零投影（ADR-057 不变）——探索族随图响应天然送达；客户端卡面分发按 prototype/kind。

### 8. 剧本（scripts/chat_scenarios.py 族新增 S-explore）
- 全链驱动：harness 组 EXPLORATION_TOOLS + 证据 reads → search → propose_candidates → propose_selects → propose_plans（ready）→ 断言图状态（三族节点出生、journey_id 归属、零边、执行面盲）+ 画布响应形状。
- fixture 纪律：真实 transcript 资产走 scenario/ 前缀（delete_project 共享 key 坑记忆）；无词级时间戳素材的降级路径同测。

## 避让清单（撞一条 = 停手问）

- 执行世界零改动：`apply_wiring_ops` / `create_run` / scope classifier / Start 四合取 / hold→capture→release / fencing（ADR-079）/ orchestrator / workflow_steps。
- 确认教义 / dock pill 唯一座 / G-1 / trigger turn 白名单 / 打字机律（新增散文字段带读容忍）/ Activity 十规则零触碰。
- propose_tasks / edit_graph / turn_tools 生产工具集 / chat_intent_system.j2 本批零改动（迭代二的事）。
- 生产 chat agent 不接 EXPLORATION_TOOLS；不加 R6 路由 prompt。
- 探索产物永不进执行拓扑 / 闭包 / 报价 rank / 媒体流边（I-EXPLORE-01）；journey_id 永不成图边。
- reasoning / CoT 永不持久化（Select 只存 verdict + 一行理由 + 证据指针）。
- 词表纪律：新词先登记 NAMING（type 值 / exploration_kind / 状态词）再进代码；裸 plan 违规 N-11 不变（Content Plan 带限定词）。
- i18n en 先 zh 镜像；卡面文案走 i18n 不硬编码；用户数据（topic/verdict/reason）原样显示。
- 画布交互律：探索卡只读展示（无拖线/连线/直改手势）；卡面 chrome 守既有发丝线/无 shadow/gray ladder 律。
- alembic：迁移文件提交入库；dev 库迁移后实证；改文件不重跑坑（版本推进后改文件无效——交付前回滚实证存储形态）。

## 验证纪律

- 会话内自跑：compileall、纯 pytest 全量（新增：探索写门 / 证据校验 / I-EXPLORE-01 / spec 形状 / reads 渲染器）、check_gates、prompt_gate（reads 注册扰动面）、web tsc + vitest（卡面 + layout）。
- 剧本 S-explore 需 dev API + worker：会话内能起则跑（harness 环境预检记忆），跑不了标「未跑验证」。
- alembic 迁移 dev 库实证（升级 + 回滚 + 存储形态）。
- 认知验收（PROGRESS §0.4 规则 9）DoD 三答：agent 看见了什么（证据 reads + 阶段视图）/ 内部表示一致吗（spec 形状 = 卡面消费形状，零投影）/ 怎么知道自己对了（完整性自检 + I-EXPLORE-01 纯测试锁）。

## 验收标准

1. 探索三族经写门出生后住持久图（journey_id 归属正确、级联删除随项目、零投影直达 graph API）。
2. 证据校验三牙全锁（start<end / 超时长拒 / excerpt 无交集拒）+ 幂等重放返回既有 artifact。
3. I-EXPLORE-01 纯测试绿：探索节点对执行闭包 / 报价 / rank / 边语义不可见；执行写门拒收 exploration 节点；探索写门拒建边。
4. 画布三族卡面按 spec 渲染（合集折叠展开 / 精选理由行 / 方案 draft 虚线 + ready 徽），无端口无边，不镜像 running。
5. search_transcript / get_segment 注册进 perception 且 prompt_gate 三探针 PASS；无时间轴素材诚实降级。
6. S-explore 剧本全链绿（或标未跑验证）。
7. 零改动清单实证：graph_store / orchestrator / scope_classifier / service.py / propose_turn.py / turn_tools.py / chat_intent_system.j2 diff 为零。

## 收口

- PROGRESS §0.1 里程碑行更新（三次迭代注册）+ §0.2 本批行；NAMING 新词注记（type 值 / exploration_kind / 状态机词）；MODULE_ARCH 表归属与写门登记。
- conventional commits，每 commit 自绿；报告 = 改动文件 / 测试 / 剩余风险 + select_clips 裁决复述。
