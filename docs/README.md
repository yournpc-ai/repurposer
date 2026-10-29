# Repurposer Docs 索引

> Status: Active navigation（2026-10-29）。
>
> 文档治理原则：**单一事实源**——每类信息只有一个家，其他文档只引用、不复述。
> **两类职责**：现行规范回答“现在必须怎样工作”；PROGRESS 与局部 progress 回答“做到哪、下一步做什么”。不维护历史、归档或逐轮报告，清理规则以 CLAUDE.md 为准。
> **去历史化律**：现行规范只承载现行法（现在时直陈），不写拍板过程、翻案链、退役史或逐轮验收数字。状态更新覆盖旧快照，不追加会话编年史；普通修复不新增 ADR，重要架构/产品决策才新增独立记录。
> 每份文档头部必须带 `> Status:` 行（状态词 + 一个更新日期戳，不叙过程）；新文档必须在本表登记。被引用的退役 ADR 编号保留别名/替代去向，不制造断链。

## 最短阅读路径

固定入口 = `../CLAUDE.md` + `PROGRESS.md` §0 + 当前任务状态/合同的相关章节。执行方式以 [CLAUDE 默认阅读与收尾协议](../CLAUDE.md#默认阅读与收尾协议) 为准：先定位标题，再读任务相关段落；引用不意味着递归通读。局部修复不要求读取全模块欠账，模块接手或发布评估才读完整状态。

| 任务范围 | 最小阅读路径 |
|---|---|
| 新 Video Project / Film/MG 架构施工 | `VIDEO_PROJECT.md` §0 长期创作方针 → `tasks/video-project-implementation.md` 当前阶段/§9 接手入口 → 目标文档命中章节；Generator 读 §4.3.2/§8.1.1，综合验收作品读施工合同 §5.1；涉及 Chat/Graph/Run 接缝再加 CHAT_ARCHITECTURE / AGENT_ARCHITECTURE 对应小节 |
| 修 Chat 显示 bug（活动 / SSE / 打字机 / dock） | `CHAT_ARCHITECTURE.md` §8（工作段重点 §8.6～§8.7）→ 命中的当前任务合同只读对应验收；工具或修订改动再选 §3 / §9 |
| UI 视觉 / 组件 / 布局 | `UI_GUIDELINES.md` 对应章节；只有涉及 chat 行为才加读 CHAT_ARCHITECTURE |
| 改 Home 货架 / 配方卡 / 样片 | `RECIPES.md` §4、§7 + `UI_GUIDELINES.md` §4.1；替换真实样片或处理入口欠账再看 `tasks/home-creation-entry-refresh.md` §2～§5 |
| 模块 / 表 / 队列 / worker | `MODULE_ARCHITECTURE.md` §4 / §5 / §7 的对应小节；迁移再加 `DATABASE_MIGRATIONS.md` |
| Agent / tools / graph / 报价 | `AGENT_ARCHITECTURE.md` §2 / §4 / §5 / §7 / §8 中对应小节 |
| 意图路由 / plan path / brief | `DIALOG_WORKFLOW.md` §2、§4 + `CHAT_ARCHITECTURE.md` §3 |
| 渲染 / clip-spec / film-spec / 编辑器 | `RENDERING.md` §3、§6、§8 中对应小节；Film 另读其总设计，编辑器交互再加 `VIDEO_EDITOR.md` |
| 积分 / 钱包 / 授权 / 估价 | `BILLING.md` 对应章节 + 当前任务涉及的确认规则 |
| 支付 / Stripe / 充值 / webhook | `PAYMENTS.md` 对应架构、凭据/部署、订单或 webhook 章节 + `tasks/stripe-credit-topup.md` 当前施工与验收 |
| 新功能 / 用户体验 | `JOURNEYS.md` 的对应旅程与缺口，不通读其他旅程；目标架构只有被动到才读 `ARCHITECTURE_NORTH_STAR.md` 对应章节 |
| 决策 / 排障 | `DECISIONS.md` 按主题和编号定点读；排障查当前代码、测试与运行证据，不依赖历史文档库 |

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
| 技术决策 | `DECISIONS.md`（ADR） | 只保留现行决策；同一决策的措辞补正与实现修复更新原条款，普通修复不新增 ADR。失效内容直接删除，不建 archive；被引用编号保留别名或替代去向 |
| 竞品证据 | `research/` + `DECISION_MATRIX.md` | `COMPETITIVE_ANALYSIS.md` 只做综合，不存原始事实 |
| 产品定位 / 需求 | `PRD.md` | 技术决策引用对应 ADR，不在 PRD 复制实现规范 |
| 现状架构 | `MODULE_ARCHITECTURE.md` + 子系统文档 | 描述"现在是什么"，不描述"将要做什么" |
| Studio UI 设计系统 | `UI_GUIDELINES.md` | 圆角/纵深/灰梯/hover/浮层冰霜/composer 视觉解剖/侧栏解剖/页面布局/画布形态只住这里；CLAUDE.md 只载高频硬律摘要 |
| 目标架构 / 可靠性主线 | `ARCHITECTURE_NORTH_STAR.md` | 只承载跨模块目标架构与可靠性主线（五态：CURRENT/TARGET/PLANNED/OPEN/REJECTED）；具体 PLANNED 产品需求、启动条件和验收仍归 PROGRESS 与当前任务合同；现状归 MODULE_ARCHITECTURE.md |
| 模块架构 / 表归属 | `MODULE_ARCHITECTURE.md` | 六层模块图 + 跨模块契约 |
| 身份/运营层概念架构 | `POSITIONING.md` | 定位根 / 人设分区 / 渠道 / 选题的概念树只住这里，其他文档只引用 |
| 对话→生产概念架构 | `DIALOG_WORKFLOW.md` | 厚 agent 判词 / 双引擎 workflow / brief / canonical 词汇（router·understand·plan）只住这里，其他文档只引用 |
| Video Project 目标架构与施工 | `VIDEO_PROJECT.md` / `tasks/video-project-implementation.md` | 目标文档 §12 唯一定义新旧目录与逐项处置，其余章节载 Project / Composition / CompositionVersion、Track/Clip/Object、Skill、全局跨 Chat 引用、旁白/字幕、Run/Graph 接缝与 video-spec 的已拍板目标；施工文档只载四阶段范围、代码接缝与验收。当前状态只见 PROGRESS §0 与施工合同；Generator 是 B-IV/V 目标，不因命名已登记而视为已实现 |
| 用户旅程 | `JOURNEYS.md` | 旅程逐拍 / 分支树 / 体验规格横切 / 缺口登记只住这里；新功能开工先答「在哪条旅程哪一拍」 |
| 积分 / 钱包 / 计费架构 | `BILLING.md` | credit / wallet / credit_transactions / hold→capture→release / configs / 比例参数 / 负余额语义只住这里，其他文档只引用 |
| 支付 / 法币订单 / Stripe | `PAYMENTS.md` | 公司账号凭据、本地 CLI 与公网 Docker 拓扑、积分包白名单、payment_orders、Checkout/webhook、入账幂等与上线门只住这里；首批欠账归 `tasks/stripe-credit-topup.md` |
| Lifecycle / Activity / Confirmation | `DECISIONS.md` ADR-087 + `CHAT_ARCHITECTURE.md` 对应章节 | 生命周期五态、活动投影与确认约束按 ADR 定点阅读；实施与验收欠账归 `PROGRESS.md`，不在导航中复制 |
| 探索产物 / Agent 工作循环 / 执行边界 | `DECISIONS.md` ADR-088/089 + `JOURNEYS.md` 旅程四 | 探索产物、Content Plan、Execution Scope、决策包与项目记忆按对应 ADR 阅读；旅程理由只住 JOURNEYS |
| 精确编辑 / 产物身份 / 版本与归档 | `DECISIONS.md` ADR-090/091 + `VIDEO_EDITOR.md` / `RENDERING.md` | 编辑解算、work/version、归档与存储不变量按改动面选读；产品版本保留是现行能力，不是文档历史 |
| 交互形态 / options / 素材等待 / transcript | `CHAT_ARCHITECTURE.md` + `DECISIONS.md` 主题索引 | 现行行为先读 Chat 对应章节；只有契约不清或冲突时才按编号查 ADR-099/100/102/108/109，仍开放的施工范围读当前任务合同 |

## 文档清单

| 文档 | 角色 | 状态 | 何时读 |
|---|---|---|---|
| `PRD.md` | 产品定位、ICP、FR 需求目录、输出规格与指标 | 活跃 | 动产品方向/需求前 |
| `PROGRESS.md` | 当前优先级、实施状态、后续能力、延期条件、需求池与上线阻塞（**排期/优先级唯一事实源**） | 活跃快照（就地更新） | 开工、排期或发布评估前 |
| `STRATEGY.md` | 战略论证：三个判断 / 三资产哲学 / 五张牌 / 两个风险 / Gallery 决策 | 活跃 | 动方向、评估新功能、仲裁排期争议时 |
| `MODULE_ARCHITECTURE.md` | 六层模块图 + 表归属契约 + 现状系统架构（代码地图/队列/数据约定） | 活跃 | 动模块边界/新模块/任何子系统前 |
| `UI_GUIDELINES.md` | **Studio 视觉/交互设计系统**：圆角与按钮 / 图标 / 浮层选型 / 卡面纵深 / 灰梯 / 浮层冰霜 / composer 视觉解剖 / 侧栏解剖 / 页面布局 / 画布形态 | 活跃 | 动 `_app` UI / 共享组件前 |
| `ARCHITECTURE_NORTH_STAR.md` | **目标架构与可靠性主线**（North Star）：Agent=Decision Producer / Execution Kernel=可靠性核心 / Structured Media=领域核心 + 执行概念词典 + 五态纪律 + 技术依赖 | 活跃 | 动执行内核、可靠性、agent 边界或 Media IR 方向时读对应章节；不是所有 coding 任务的通用全文前置 |
| `POSITIONING.md` | 定位根概念架构（运营层母文档）：定位/人设/渠道/选题概念树 + 产品流程 + 实施范围 | 已拍板方向（ADR-042），未实施；启动条件与验收归 `PROGRESS.md` §1.1 | 动身份模块/渠道/选题/home 前 |
| `VIDEO_PROJECT.md` | **视频作品目标架构**：Project / Composition / CompositionVersion、Scene/Storyboard、Track/Clip/Object、Animation/TextPart、Skill/VideoTemplate、SourceSnapshot、全局 @ 引用、旁白/字幕、Graph/Run 接缝与 video-spec | 已拍板目标（ADR-145）；§0 为各阶段必读方针，当前实现/欠账归 PROGRESS 与 `tasks/video-project-implementation.md`，不以目标目录冒充实现 | 新 Film/MG 架构、视频 CRUD、Skill、时间/动画或渲染替换施工前 |
| `AGENT_ARCHITECTURE.md` | 四层工程地图（Model / Harness / Graph / Loop，ADR-039）+ 工具包/花名册/NodeBase/估价 | 活跃 | 动 generation/agents/tools 前 |
| `DIALOG_WORKFLOW.md` | 对话→生产概念架构母文档：双引擎 workflow / canonical 词汇 / brief + ask_user / 有界 loop 节点 | 现行规范（实现状态以 `PROGRESS.md` 为准） | 动 chat 意图层 / plan path / 多轮对话 / agent 概念前 |
| `VIDEO_EDITOR.md` | 编辑器交互形态 + L2/L3 范围纪律 | 已实现（undo 可用 = operations 端点 + chat 撤销；编辑面分层=能力层+适配层，ADR-033） | 动编辑器前 |
| `RENDERING.md` | **clip-spec / film-spec / video-spec 迁移期家族契约** + 渲染链架构（烘焙缝 / 渲染服务 / 共享包 / 函数地图）+ clip-spec 轨道模型（§8 = 现行契约，ADR-044） | 活跃 | 动渲染链、任一 spec family、轨道或渲染服务前 |
| `MUSIC_ARCHITECTURE.md` | 音乐库、人设音乐选择、自定义生成与启动 reconcile | 当前实现： persona 皮肤面板可自定义生成，Chat `add_music` 只选库；prompt 缓存、配额、上传与更多入口 deferred | 动音乐前 |
| `BILLING.md` | 积分/钱包/计费架构母文档（ADR-055）：credit / wallet / credit_transactions + hold→capture→release + configs + live ratio + 负余额语义；支付与订阅边界分别指向 PAYMENTS / PROGRESS | 活跃 | 动积分 / 钱包 / configs / 扣费 / 估价展示前 |
| `PAYMENTS.md` | 支付架构母文档：公司 Stripe 凭据与本地/公网拓扑、积分包、payment_orders、Checkout/webhook、purchase 幂等、前端购买座位与上线门 | 当前规范；首批已落码，联调欠账归 `tasks/stripe-credit-topup.md` | 动支付、充值、Stripe、webhook、退款或订阅前 |
| `DECISIONS.md` | 现行架构决策集（ADR；编号不连续，主题索引 + 定点阅读；退役引用保留替代去向） | 活跃 | 新决策 / 架构约束变化时按编号读；普通 bug 修复、字段接线、测试结果不新增 ADR，不要求通读全文 |
| `DECISION_MATRIX.md` | 竞品能力 → 采纳/改造/不做矩阵 | 活跃 | 评估竞品功能时 |
| `DISTRIBUTION.md` | 分发模块设计：数据模型 / 状态机 / OAuth / 发布对话框 / 通知 / 回流边界 | 直发链路代码已落；平台凭据、审批与真实联调随 R1.1 挂起 | 动 Distribution 前 |
| `NAMING.md` | 命名宪法：八条 + 词汇表 + 判例库 | 活跃 | 任何新名字（表/字段/包/skill/API）前；命名争议仲裁 |
| `CHAT_ARCHITECTURE.md` | Agent Interface 层 + **chat/画布行为唯一事实源**：tool registry / plan path / QuestionDock / SSE / 打字机律 / Candidate Surface / 两形态机 / mentions / 词表 v3 / 相机律 / 修订边界 | 活跃；live 验收欠账归当前任务合同 | 动 chat / dock / 画布行为 / registry / 进度推送前 |
| `JOURNEYS.md` | **用户旅程母文档**：四条旅程逐拍 × 分支树 × 系统支撑表 × 缺口登记（ADR-077/078 与 ADR-088/089 的立项依据） | 活跃 | 新功能或体验改动前读对应旅程与缺口；技术评审倒查「让哪条旅程哪一拍变好」，不要求通读全部旅程 |
| `MENTIONS.md` | @ 提及体系方针：请求 / 指认两族（当前 asset / output / workflow_step）+ 排除清单（配方、产出类型、自由参数、人设不新建成 mention）+ 判定三问 + @tool 立案方针 | 活跃 | 任何新 mention 类型立案前 |
| `RECIPES.md` | 配方与 Home 货架母文档：prompt-only 发射、服务端 registry 与前端货架职责、caption catalog、dub/reframe/quote 链、样片证据分级与 R5 延期边界 | 当前规范；Home 真片/占位片与验收状态归 `tasks/home-creation-entry-refresh.md` | 动首页配方卡、字幕样式、dub/合成视频/分镜能力前 |
| `COMPETITIVE_ANALYSIS.md` | 七家竞品综合（Round 1.2） | 活跃 | 竞品概览 |
| `LANDING.md` | 落地页叙事工作文档：当前结构与 hero + 单助手叙事立场 + 隐藏面恢复条件 + 六幕叙事骨架（缓做） | 活跃 | 动落地页结构/hero/叙事前 |
| `API.md` | API 参考 | 活跃 | 对接口前 |
| `VERIFICATION.md` | 测试政策、fixture/配额、合同守卫映射与共享验收；新视频按 A/B 合同补覆盖，旧实现锁不作兼容目标 | 当前规范，未运行项明确保留 | 改测试、共享机制、验收或裁决退役测试前 |
| `DATABASE_MIGRATIONS.md` | Alembic 工作流 | 活跃 | 写迁移前 |
| `PRODUCTION_DEBUGGING.md` | 生产事故只读取证手册：分层日志 / 容器环境 / 网页采集签名 / 数据库只读检查 / 部署后验收 | 活跃 | 线上排障、部署验收前 |
| `research/` | 竞品卡片（7 家）+ Opus 深拆 + ElevenCreative 调研 + FLORA 首页/工作台走查 + Lovart 落地页走查 + MiniMax Design 走查 + Agent Skills 规范生态 + 渲染技术调研 + dsh 架构调研 + craft 解剖证据表 | 原始素材层 | 引用证据时 |
| `tasks/` | 仍有实施或验收欠账的单功能合同：当前范围、约束、依赖、禁止事项与可执行验收。`VERIFICATION.md` 另作为验证合同登记表与跨模块验收尾项的唯一座位使用 | 活跃 | 只读当前任务命中的合同；长期约束归母文档，共享验收归 VERIFICATION，tasks 只保留仍有独立实施范围的当前合同，不留过程副本 |

## 已规划的文档（尚未撰写）

- `METRICS.md` — 产品度量：漏斗（上传→生成→精修→发布→回流）、事件埋点、各阶段成功指标
