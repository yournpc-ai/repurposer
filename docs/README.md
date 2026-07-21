# Repurposer Docs 索引

> 文档治理原则：**单一事实源**——每类信息只有一个家，其他文档只引用、不复述。
> 每份文档头部必须带 `> Status:` + 日期行；新文档必须在本表登记。

## 信息类型 → 唯一事实源

| 信息类型 | 唯一事实源 | 规则 |
|---|---|---|
| 排期 / 优先级 | `ROADMAP.md` | 其他文档只准引用条目号 |
| 战略论证（为什么做 / 不做什么） | `STRATEGY.md` | 其他文档只引用条目号（`STRATEGY §X`），不复述论证 |
| 技术决策 | `DECISIONS.md`（ADR） | 只追加，不修改旧 ADR；翻案写新 ADR 并标注 supersedes |
| 竞品证据 | `research/` + `DECISION_MATRIX.md` | `COMPETITIVE_ANALYSIS.md` 只做综合，不存原始事实 |
| 产品定位 / 需求 | `PRD.md` | 技术决策内容降级为指向 ADR 的指针 |
| 现状架构 | `ARCHITECTURE.md` + 子系统文档 | 描述"现在是什么"，不描述"将要做什么" |
| 模块架构 / 表归属 | `MODULE_ARCHITECTURE.md` | 六层模块图 + 跨模块契约 |

## 文档清单

| 文档 | 角色 | 状态 | 何时读 |
|---|---|---|---|
| `PRD.md` | 产品定位、FR 需求、竞品借鉴 | 活跃（2026-07 瘦身：技术章节移至 ARCHITECTURE/API） | 动产品方向/需求前 |
| `ROADMAP.md` | 分模块需求排期（8 模块表 + 依赖图 + P0 汇总） | 活跃（2026-07 建） | 排期/开工前 |
| `STRATEGY.md` | 战略论证：三个判断 / 三资产哲学 / 五张牌 / 两个风险 / Gallery 决策 | 活跃（2026-07-21 建） | 动方向、评估新功能、仲裁排期争议时 |
| `ARCHITECTURE.md` | 系统现状架构 | 活跃 | 动任何子系统前 |
| `MODULE_ARCHITECTURE.md` | 六层模块图 + 表归属契约（"2027 架构"） | 活跃（2026-07 建） | 动模块边界/新模块前 |
| `AGENT_ARCHITECTURE.md` | 4-layer 生成编排（Layer 4 未实现，图已标注） | 已实现 | 动 generation/agents 前 |
| `VIDEO_EDITOR.md` | clip-spec 契约 + 编辑器范围纪律 | 已实现（undo 待 Operation Model） | 动编辑器/渲染前 |
| `MUSIC_ARCHITECTURE.md` | AI 音乐库 | 已实现（Layer-4 音乐校验仍 future） | 动音乐前 |
| `DECISIONS.md` | ADR-001 ~ ADR-025 | 持续追加 | 翻案/新决策时 |
| `DECISION_MATRIX.md` | 竞品能力 → 采纳/改造/不做矩阵 | 活跃 | 评估竞品功能时 |
| `COMPETITIVE_ANALYSIS.md` | 七家竞品综合（Round 1.2） | 活跃 | 竞品概览 |
| `API.md` | API 参考 | 活跃 | 对接口前 |
| `DATABASE_MIGRATIONS.md` | Alembic 工作流 | 活跃 | 写迁移前 |
| `research/` | 竞品卡片（7 家）+ Opus 深拆 + 渲染技术调研 | 原始素材层 | 引用证据时 |
| `tasks/` | 单功能实施简报（含 Prohibited Behaviors） | 活跃 | 开工对应功能前必读 |

> MVP 时代文档（`MVP_SPEC.md`、`SCHEDULE.md`）已于 2026-07-20 逐节 review 后删除：可保留的信息已迁入 CLAUDE.md（composer 行为契约 / Brand=视觉皮肤 / demo 运维注意事项）与 MODULE_ARCHITECTURE.md（精修三角），其余章节确认被新体系覆盖或已过时（如"不做 LLM 意图识别"），需要时从 git 历史查阅。

## 已规划的文档（尚未撰写）

- `CHAT_ARCHITECTURE.md` — Agent Interface 层：意图 → 操作 dispatch、chat 何时产生 editor 操作 vs 触发重生成
- Distribution 数据模型设计 — Publication / ChannelAccount / 审核队列状态机
