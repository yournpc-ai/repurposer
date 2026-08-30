# Repurposer Docs 索引

> 文档治理原则：**单一事实源**——每类信息只有一个家，其他文档只引用、不复述。
> 每份文档头部必须带 `> Status:` + 日期行；新文档必须在本表登记。

## 信息类型 → 唯一事实源

| 信息类型 | 唯一事实源 | 规则 |
|---|---|---|
| 排期 / 优先级 / 需求池 | `PROGRESS.md` | 其他文档只准引用周次或需求池条目 |
| 战略论证（为什么做 / 不做什么） | `STRATEGY.md` | 其他文档只引用条目号（`STRATEGY §X`），不复述论证 |
| 技术决策 | `DECISIONS.md`（ADR） | 只保留现行决策：过时 / 被翻案的内容直接删除（历史在 git，不留痕）；新决策追加新编号 |
| 竞品证据 | `research/` + `DECISION_MATRIX.md` | `COMPETITIVE_ANALYSIS.md` 只做综合，不存原始事实 |
| 产品定位 / 需求 | `PRD.md` | 技术决策内容降级为指向 ADR 的指针 |
| 现状架构 | `MODULE_ARCHITECTURE.md` + 子系统文档 | 描述"现在是什么"，不描述"将要做什么" |
| 模块架构 / 表归属 | `MODULE_ARCHITECTURE.md` | 六层模块图 + 跨模块契约 |
| 身份/运营层概念架构 | `POSITIONING.md` | 定位根 / 人设分区 / 渠道 / 选题的概念树只住这里，其他文档只引用 |

## 文档清单

| 文档 | 角色 | 状态 | 何时读 |
|---|---|---|---|
| `PRD.md` | 产品定位、ICP、FR 需求目录、输出规格与指标 | 活跃（2026-07-31 二度瘦身：§3.4/§6 删除，FR 表压缩为目录） | 动产品方向/需求前 |
| `PROGRESS.md` | 进展快照 + 排期（至 10-23 go/no-go）+ 需求池（**排期/优先级唯一事实源**；双受众：内部管理/投资人可摘录） | 活跃快照（每周五滚动；周期结束归档） | 排期/开工前；向上汇报 / 逐日执行对齐时 |
| `STRATEGY.md` | 战略论证：三个判断 / 三资产哲学 / 五张牌 / 两个风险 / Gallery 决策 | 活跃（2026-07-21 建） | 动方向、评估新功能、仲裁排期争议时 |
| `MODULE_ARCHITECTURE.md` | 六层模块图 + 表归属契约（"2027 架构"）+ 现状系统架构（代码地图/队列/数据约定，自 ARCHITECTURE.md 并入） | 活跃（2026-07 建） | 动模块边界/新模块/任何子系统前 |
| `POSITIONING.md` | 定位根概念架构（运营层母文档）：定位/人设/渠道/选题概念树 + 产品流程重写 + 实施切分 | 已拍板方向（2026-08-13，ADR-042），未实施——排期 PROGRESS 第六~八周 | 动身份模块/渠道/选题/home 前 |
| `AGENT_ARCHITECTURE.md` | 四层工程地图（Model / Harness / Graph / Loop，ADR-039）+ 技能包/花名册/NodeBase/估价 | 活跃（2026-08-09 重画；2026-08-18 随 ADR-043 收口请求层语法） | 动 generation/agents/skills 前 |
| `VIDEO_EDITOR.md` | 编辑器交互形态 + L2/L3 范围纪律 | 已实现（undo 已随 Operation Model 落地；editor 内 undo 按钮后置；编辑面分层=能力层+适配层，ADR-033） | 动编辑器前 |
| `RENDERING.md` | **clip-spec 字段级契约** + 渲染链架构（烘焙缝 / 渲染服务 / 共享包 / 函数地图）+ 轨道模型（§8 = 现行契约，ADR-044） | 活跃（2026-08-17 建；契约自 VIDEO_EDITOR §4 迁入；轨道模型 ADR-044 08-17 过会、08-17~18 落地） | 动渲染链/clip-spec/轨道/渲染服务前 |
| `MUSIC_ARCHITECTURE.md` | AI 音乐库 | 已实现（Layer-4 音乐校验仍 future） | 动音乐前 |
| `DECISIONS.md` | 现行架构决策集（ADR；编号不连续——过时条目直接删除，历史在 git） | 活跃 | 新决策 / 架构约束变化时 |
| `DECISION_MATRIX.md` | 竞品能力 → 采纳/改造/不做矩阵 | 活跃 | 评估竞品功能时 |
| `DISTRIBUTION.md` | 分发模块设计：数据模型 / 状态机 / OAuth / 审核队列 / 回流 | 活跃（2026-07-21 建；直发链路代码完成 07-24，待平台凭据联调） | 动 Distribution 前 |
| `NAMING.md` | 命名宪法：八条 + 词汇表 + 判例库 | 活跃（2026-07-25 建） | 任何新名字（表/字段/包/skill/API）前；命名争议仲裁 |
| `CHAT_ARCHITECTURE.md` | Agent Interface 层：task list 契约 / skill registry / compile_graph 动态物化 / SSE / mentions / edit ops（ADR-032） | v2 已实现（2026-07-26：chat UI + RunCard + edit ops 接线；plan 级节点重跑 📋） | 动 chat / registry / 进度推送前 |
| `INTENT_COVERAGE.md` | 意图层覆盖全景：单一表面（/chat）× 七类意图的全分叉矩阵 + 状态（✅🚧❌）+ 缺口登记表 + 测试矩阵 | 活跃（2026-07-30 建；**2026-08-04 意图层单面化**——/intent 退役、任务书并入 plan path，简报 `tasks/intent-surface-unification.md`） | 加 chat 能力 / 评估意图缺口 / 写 chat 相关 e2e 前 |
| `MENTIONS.md` | @ 提及体系方针：两族分类（请求 / 指认）+ 排除清单（配方/产出/参数/人设永不是 mention）+ 判定三问 + @skill 方针 | 活跃（2026-08-11 建） | 任何新 mention 类型立案前 |
| `RECIPES.md` | 配方架构母文档：home 能力演示卡 + 兑现管线（caption catalog / dub 接线 / voice_gen / 分镜指引）+ R1–R6 分期 | 🚧 R1/R2/R6 已落地、8 卡全 live；**画廊 v3（2026-08-27 拍板，ADR-048——三轴模型 + 招牌菜组织原则 + 三级闸门，八卡六形态，§4/§7 已同步）**；R3–R5 待施工；Remix = overlay 内发射 + 预填模板载荷（配方 = 提示词，ADR-040 / MENTIONS §3） | 动首页配方卡、字幕样式、dub/合成视频/分镜能力前；配方线 tasks 简报的母文档 |
| `COMPETITIVE_ANALYSIS.md` | 七家竞品综合（Round 1.2） | 活跃 | 竞品概览 |
| `LANDING.md` | 落地页叙事工作文档：现状结构 + 叙事立场（单助手）+ 待拍板（hero 四方向）+ 迭代清单（含六幕叙事骨架，缓做） | 活跃（2026-08-19 建） | 动落地页结构/hero/叙事前 |
| `API.md` | API 参考 | 活跃（2026-08-18 全面对齐路由） | 对接口前 |
| `DATABASE_MIGRATIONS.md` | Alembic 工作流 | 活跃 | 写迁移前 |
| `research/` | 竞品卡片（7 家）+ Opus 深拆 + ElevenCreative 调研 + FLORA 首页/工作台走查 + **Lovart 落地页走查（`lovart-landing.md`——hero 任务轮播 + 滚动驱动「输入→prompt→输出」demo 幕，着陆叙事证据）** + MiniMax Design 走查（界面工艺清单 + Skills 仓库解剖）+ Agent Skills 规范生态（Mastra/Agno 文档证据，`agent-skills-spec.md`）+ 渲染技术调研 + dsh 架构调研（agent harness 对照，采纳项已分流 PROGRESS/NAMING/AGENT_ARCH）+ **craft 解剖证据表（`craft-anatomy-2026-08-22.md`——产物质量线期 0 产出，四卡 × 真素材三源测量，期 2/3 施工顺序由它决定）** | 原始素材层 | 引用证据时 |
| `tasks/` | 单功能实施简报（含 Prohibited Behaviors）；已完成简报归 `tasks/done/`（历史记录，不再维护） | 活跃 | 开工对应功能前必读 |

## 已规划的文档（尚未撰写）

- `METRICS.md` — 产品度量：漏斗（上传→生成→精修→发布→回流）、事件埋点、各阶段成功指标
- `BILLING.md` — 套餐经济设计：档位 / 免费额度 / credits↔产出换算 / 对外成本预估呈现；预算帽路由参照（elevencreative §8 机制 6"自动低于300积分"）
