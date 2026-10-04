# Repurposer Docs 索引

> 文档治理原则：**单一事实源**——每类信息只有一个家，其他文档只引用、不复述。
> **去历史化律**：正文只承载现行法（现在时直陈）——不写日期、拍板过程、翻案链、退役史、试错史；历史在 git，决策编号在 `DECISIONS.md`（ADR 裸引用合法）。例外：竞品/证据文档的时间线即内容；`archive/` 是历史的合法居所。
> 每份文档头部必须带 `> Status:` 行（状态词 + 一个更新日期戳，不叙过程）；新文档必须在本表登记。

## 架构金字塔（常驻导航）

> **任何需求 / 概念 / 评审，先在金字塔上定位它属于哪一层。** 金字塔是常驻的：层的归层——新词进对应层文档，新层才动本表。

```
┌─ 愿景层：Agentic Content OS（对外叙事 + 愿景↔现行对照表）—— ARCHITECTURE_NORTH_STAR.md §1 / §1.1
├─ 概念层：执行五概念 + 内容世界六概念词典 —— NORTH_STAR §2 / §2.1（加词先过 NAMING.md）
├─ 方向层：五态（CURRENT / TARGET / PLANNED / OPEN / REJECTED）—— NORTH_STAR §3~§9
├─ 模块层：六层模块图 + 表归属契约 —— MODULE_ARCHITECTURE.md
├─ 工程层：Model / Harness / Graph / Loop 四层地图 —— AGENT_ARCHITECTURE.md
├─ 旅程/排期层：用户旅程 —— JOURNEYS.md ｜ 当前批次 —— PROGRESS.md §0
└─ 代码层：apps/api/app/（经表归属契约查到文件）
```

**定位规则**：
1. 新需求 → 先答两问：「动金字塔哪一层」+「JOURNEYS 哪条旅程哪一拍」——两问都答不上 = 需求还没想清楚，不立项；
2. 新概念词 → 归对应层文档的词典/契约；禁止在层外发明平行词汇；
3. 愿景词 → 先查 §1.1 对照表有没有现行座位；**没有座位的愿景词不许落进代码命名**（词汇版「把 OPEN 写成 CURRENT」）；
4. 某层发生变化 → 同批更新该层文档；层结构本身变化 → 才动本表。

## 信息类型 → 唯一事实源

| 信息类型 | 唯一事实源 | 规则 |
|---|---|---|
| 排期 / 优先级 / 需求池 | `PROGRESS.md` | 其他文档只准引用周次或需求池条目 |
| 战略论证（为什么做 / 不做什么） | `STRATEGY.md` | 其他文档只引用条目号（`STRATEGY §X`），不复述论证 |
| 技术决策 | `DECISIONS.md`（ADR） | 只保留现行决策：过时 / 被翻案的内容直接删除（历史在 git，不留痕）；新决策追加新编号 |
| 竞品证据 | `research/` + `DECISION_MATRIX.md` | `COMPETITIVE_ANALYSIS.md` 只做综合，不存原始事实 |
| 产品定位 / 需求 | `PRD.md` | 技术决策内容降级为指向 ADR 的指针 |
| 现状架构 | `MODULE_ARCHITECTURE.md` + 子系统文档 | 描述"现在是什么"，不描述"将要做什么" |
| Studio UI 设计系统 | `UI_GUIDELINES.md` | 圆角/纵深/灰梯/hover/浮层冰霜/composer 视觉解剖/侧栏解剖/页面布局/画布形态只住这里；CLAUDE.md 只载高频硬律摘要 |
| 目标架构 / 可靠性主线 | `ARCHITECTURE_NORTH_STAR.md` | "将要建成什么"只住这里（五态纪律：CURRENT/TARGET/PLANNED/OPEN/REJECTED）；现状描述仍归 MODULE_ARCHITECTURE.md |
| 模块架构 / 表归属 | `MODULE_ARCHITECTURE.md` | 六层模块图 + 跨模块契约 |
| 身份/运营层概念架构 | `POSITIONING.md` | 定位根 / 人设分区 / 渠道 / 选题的概念树只住这里，其他文档只引用 |
| 对话→生产概念架构 | `DIALOG_WORKFLOW.md` | 厚 agent 判词 / 双引擎 workflow / brief / canonical 词汇（router·understand·plan）只住这里，其他文档只引用 |
| 用户旅程 | `JOURNEYS.md` | 旅程逐拍 / 分支树 / 体验规格横切 / 缺口登记只住这里；新功能开工先答「在哪条旅程哪一拍」 |
| 积分 / 钱包 / 计费架构 | `BILLING.md` | credit / wallet / credit_transactions / hold→capture→release / configs / 比例参数 / 负余额语义只住这里，其他文档只引用 |
| Lifecycle / Lifecycle Projection / PLAN_READY / CONFIRMATION_READY / Activity / Activity Projection / Confirmation Doctrine | `DECISIONS.md`（ADR-087） | 五条原则 / Lifecycle 五态合同 / Activity 十条对账规则 / 确认教义 / 依赖方向只住这里；NAMING.md §2 有词汇行，其他文档只引用 |
| 探索产物 / Candidate Set / Select / Content Plan / Execution Scope / Decision Package / Confirmed Scope Snapshot / Work Session / 停顿定律 / 项目记忆分层 | `DECISIONS.md`（ADR-088/089）+ `JOURNEYS.md` 旅程四 | 探索产物族 / 双写门 / I-EXPLORE-01 / 双状态机 / 记忆四层合同只住 ADR-088；能力编译 / 决策包 / 快照 / 停顿定律 / 迁移弧只住 ADR-089；「为什么这样裁」只住旅程四；NAMING.md §2 + N-55 有词汇行，其他文档只引用 |
| edit_output / quote→range / work / version / archived / confirm_strategy | `DECISIONS.md`（ADR-090/091/092） | 精确编辑词表与解算语义只住 ADR-090；产物两身份与归档不变量只住 ADR-091；计费偏好三档与确认闸座位只住 ADR-092；其他文档只引用 |
| work_key / artifact_key / artifact_role / deliverable / facet / companion / render owner / artifact readiness | `DECISIONS.md`（ADR-096/097） | 渲染所有权编译期声明 / defer 律删除 / 就绪三合取 / track 原子写 / 恢复纪律只住 ADR-096；Artifact 分层 / 归属 stamp 律（读层禁推断）/ 两层门 / 迟晋升 / 修订不变量 / lineage 边界只住 ADR-097；其他文档只引用 |
| 终态交互形态谱系 / answer+suggestions / suggestion_ref / source_state / 交互宪法 / 言语提交协议 | `DECISIONS.md`（ADR-099；选项唯一座位翻案 = ADR-100） | 四层边界 / 形态谱系表 / 点选 provenance / 宪法六条与准入闸 / 契约车道判别式 / speech commit protocol / 默认值五词清单只住 ADR-099；**消息流零选项、固定选项全归 dock（answer+suggestions 形态翻案拆除）只住 ADR-100**（已拍板待施工，合同 `tasks/options-dock-only.md`）；施工合同 `tasks/interaction-architecture.md`（迁移收口后现行法归 CHAT_ARCHITECTURE.md）；其他文档只引用 |

## 文档清单

| 文档 | 角色 | 状态 | 何时读 |
|---|---|---|---|
| `PRD.md` | 产品定位、ICP、FR 需求目录、输出规格与指标 | 活跃 | 动产品方向/需求前 |
| `PROGRESS.md` | 进展快照 + 排期（至 10-29 go/no-go）+ 需求池（**排期/优先级唯一事实源**；双受众：内部管理/投资人可摘录） | 活跃快照（每周五滚动；周期结束归档） | 排期/开工前；向上汇报 / 逐日执行对齐时 |
| `archive/` | 历史归档区：周期实记（`PROGRESS-2026-cycle1.md`）+ 过期节点快照 + `tasks-done/`（已完成施工简报）——历史记录，不再维护，不进默认 context | 归档 | 追溯历史时 |
| `STRATEGY.md` | 战略论证：三个判断 / 三资产哲学 / 五张牌 / 两个风险 / Gallery 决策 | 活跃 | 动方向、评估新功能、仲裁排期争议时 |
| `MODULE_ARCHITECTURE.md` | 六层模块图 + 表归属契约 + 现状系统架构（代码地图/队列/数据约定） | 活跃 | 动模块边界/新模块/任何子系统前 |
| `UI_GUIDELINES.md` | **Studio 视觉/交互设计系统**：圆角与按钮 / 图标 / 浮层选型 / 卡面纵深 / 灰梯 / 浮层冰霜 / composer 视觉解剖 / 侧栏解剖 / 页面布局 / 画布形态 | 活跃 | 动 `_app` UI / 共享组件前 |
| `ARCHITECTURE_NORTH_STAR.md` | **目标架构与可靠性主线**（North Star）：Agent=Decision Producer / Execution Kernel=可靠性核心 / Structured Media=领域核心 + 执行五概念词典 + 五态纪律 + 实施序列 | 活跃 | 任何 coding agent 开工前第一读；动执行内核/agent 边界/Media IR 方向前 |
| `POSITIONING.md` | 定位根概念架构（运营层母文档）：定位/人设/渠道/选题概念树 + 产品流程重写 + 实施切分 | 已拍板方向（ADR-042），未实施——排期 PROGRESS 第八~十周运营端 | 动身份模块/渠道/选题/home 前 |
| `AGENT_ARCHITECTURE.md` | 四层工程地图（Model / Harness / Graph / Loop，ADR-039）+ 工具包/花名册/NodeBase/估价 | 活跃 | 动 generation/agents/tools 前 |
| `DIALOG_WORKFLOW.md` | 对话→生产概念架构母文档（厚 agent 蓝图，ADR-052）：双引擎 workflow / canonical 词汇（router·understand·plan·brief）/ brief + ask_user 一等终态工具 / 预填评审卡 / 有界 loop 节点 + 施工切分 B1~B4 | 已落地 | 动 chat 意图层 / plan path / 多轮对话 / agent 概念前 |
| `VIDEO_EDITOR.md` | 编辑器交互形态 + L2/L3 范围纪律 | 已实现（undo 可用 = operations 端点 + chat 撤销；编辑面分层=能力层+适配层，ADR-033） | 动编辑器前 |
| `RENDERING.md` | **clip-spec 字段级契约** + 渲染链架构（烘焙缝 / 渲染服务 / 共享包 / 函数地图）+ 轨道模型（§8 = 现行契约，ADR-044） | 活跃 | 动渲染链/clip-spec/轨道/渲染服务前 |
| `MUSIC_ARCHITECTURE.md` | AI 音乐库 | 已实现（Layer-4 音乐校验仍 future） | 动音乐前 |
| `BILLING.md` | 积分/钱包/计费架构母文档（ADR-055）：credit / wallet / credit_transactions + hold→capture→release + configs 公共参数表 + 消耗比例参数 + 负余额语义；支付只留 W11 边界 | 活跃 | 动积分 / 钱包 / configs / 扣费 / 估价展示前 |
| `DECISIONS.md` | 现行架构决策集（ADR；编号不连续——过时条目直接删除，历史在 git） | 活跃 | 新决策 / 架构约束变化时 |
| `DECISION_MATRIX.md` | 竞品能力 → 采纳/改造/不做矩阵 | 活跃 | 评估竞品功能时 |
| `DISTRIBUTION.md` | 分发模块设计：数据模型 / 状态机 / OAuth / 审核队列 / 回流 | 活跃（直发链路代码完成，待平台凭据联调） | 动 Distribution 前 |
| `NAMING.md` | 命名宪法：八条 + 词汇表 + 判例库 | 活跃 | 任何新名字（表/字段/包/skill/API）前；命名争议仲裁 |
| `CHAT_ARCHITECTURE.md` | Agent Interface 层 + **chat/画布行为唯一事实源**：终态工具集 / plan path / QuestionDock / SSE / 打字机律 / 三形态机 / mentions 运行态 / 词表 v3 / 相机律 / 修订边界 | 活跃（v2 已实现） | 动 chat / dock / 画布行为 / registry / 进度推送前 |
| `JOURNEYS.md` | **用户旅程母文档**：四条旅程逐拍 × 分支树 × 系统支撑表 × 缺口登记（ADR-077/078 与 ADR-088/089 的立项依据） | 活跃 | 任何新功能开工前；技术评审倒查「让哪条旅程哪一拍变好」 |
| `INTENT_COVERAGE.md` | 意图层覆盖全景 | **历史 / retired（ADR-087）**——不再作为 architecture authority；意图路由现状 = CHAT_ARCHITECTURE + DECISIONS | 追溯历史时 |
| `MENTIONS.md` | @ 提及体系方针：两族分类（请求 / 指认）+ 排除清单（配方/产出/参数/人设永不是 mention）+ 判定三问 + @skill 方针 | 活跃 | 任何新 mention 类型立案前 |
| `RECIPES.md` | 配方架构母文档：home 能力演示卡 + 兑现管线（caption catalog / dub 接线 / voice_gen / 分镜指引）+ R1–R6 分期 | 🚧 R1/R2/R6 已落地、8 卡全 live（画廊三轴模型 + 三级闸门，ADR-048）；R3–R5 待施工；Remix = overlay 内发射 + 预填模板载荷（配方 = 提示词，ADR-040 / MENTIONS §3） | 动首页配方卡、字幕样式、dub/合成视频/分镜能力前；配方线 tasks 简报的母文档 |
| `COMPETITIVE_ANALYSIS.md` | 七家竞品综合（Round 1.2） | 活跃 | 竞品概览 |
| `LANDING.md` | 落地页叙事工作文档：现状结构 + 叙事立场（单助手）+ 待拍板（hero 四方向）+ 迭代清单（含六幕叙事骨架，缓做） | 活跃 | 动落地页结构/hero/叙事前 |
| `API.md` | API 参考 | 活跃 | 对接口前 |
| `DATABASE_MIGRATIONS.md` | Alembic 工作流 | 活跃 | 写迁移前 |
| `research/` | 竞品卡片（7 家）+ Opus 深拆 + ElevenCreative 调研 + FLORA 首页/工作台走查 + Lovart 落地页走查 + MiniMax Design 走查 + Agent Skills 规范生态 + 渲染技术调研 + dsh 架构调研 + craft 解剖证据表 | 原始素材层 | 引用证据时 |
| `tasks/` | 单功能实施简报（含 Prohibited Behaviors）；已完成简报归 `archive/tasks-done/`。**例外：`tasks/verification-contracts.md` 不是简报——验证侧合同登记表**：合同 ↔ Owner ↔ 纯测试/剧本/静态门座 ↔ Status + Known Variance 登记 + 剧本 fixture 律；测试/断言迁移前先查它。R1/R1.1 施工合同 = `tasks/r1-*.md` / `tasks/r1-1-*.md`——每批一份自包含合同（product goal / current state / tasks / Do NOT touch / acceptance / docs update），批次存在性与顺序归 `PROGRESS.md` §0，合同只描述怎么施工 | 活跃 | 开工对应功能前必读；**新 coding session 入口 = `PROGRESS.md` §0 → 当前 batch 合同** |

## 已规划的文档（尚未撰写）

- `METRICS.md` — 产品度量：漏斗（上传→生成→精修→发布→回流）、事件埋点、各阶段成功指标
