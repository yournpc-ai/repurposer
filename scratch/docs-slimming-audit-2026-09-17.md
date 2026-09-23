# Docs Slimming 审计报告（Census-only，未改任何文件）

> 审计基线：HEAD `6a3efe9`（+ 工作区未提交改动），审计日 2026-09-17。
> 基准尺 = `docs/README.md` 治理表（单一事实源 / 历史在 git / 架构金字塔）——不是外部提案的五层分类。
> 方法：9 个并行审计 agent 逐文件通读 + grep/glob 代码实证抽查 + 关键词密度扫描；三份架构核心文档（NORTH_STAR / DIALOG_WORKFLOW / AGENT_ARCHITECTURE）由主会话精读。

---

## 0. 总账

| 口径 | 当前 | 建议后 | 变化 |
|---|---|---|---|
| docs/ 根 *.md 总量 | ~1263KB（27 份） | ~660KB（26 份，REPORT 出域） | **-48%** |
| docs/ 目录总量（含 research/ + tasks/） | ~2.2MB | ~0.9MB | **-60%** |
| DECISIONS.md | 341KB / 78 条 | ~150~170KB / **68 条** | -50~56% |
| PROGRESS.md | 321KB | ~55~65KB | **-80%** |
| tasks/ 活跃位 | 30 份（~23 份已完工未归档） | ~8 份（7 份 R1/R1.1 合同 ± 真在施工） | — |
| tasks/done/ | 350KB 留在 docs/ 内 | 整体移 `archive/` | 出域 |

**默认 coding context 变化**：入口链（README → PROGRESS §0 → batch 合同）长度不变（~31KB），但三个风险面消失：① 全量读 PROGRESS 的代价 321KB→60KB；② grep/glob 不再吸入 tasks/done/ 350KB + REPORT；③ 查 ADR 不再踩翻案残文（341KB→~160KB 且条目净减 10）。若按"架构全读"场景（README+PROGRESS+NORTH_STAR+MODULE+AGENT+DIALOG+CHAT_ARCH+DECISIONS）：846KB → ~140KB，**-83%**。

**审计中顺手发现的 drift 实证**（比臃肿更该先修）：
1. 剧本测试数量三文档三说法且全错：AGENT_ARCH "S1–S12" / NORTH_STAR "S1–S17" / PROGRESS "S1–S12" vs 代码实况 24 本（S1–S22 + S25/S26 + S40–S42 + S53）。
2. ADR-025 接口名与代码漂移（ADR 写 `generate_structured`/`chat_with_tools`，代码是 `generate`/`generate_with_tools`）。
3. ADR-042 已决未实施（personas 表仍在、无 positionings/topics 表）但无 Pending 标注——coding agent 有按"定位根改名"误改代码的风险。
4. MODULE_ARCH §7.1 代码地图 1/29 失效（`clients/minimax.py` 旧路径残留，实际在 `providers/llm/`）。
5. API.md 章节号错乱（两个 §4/§5/§11）。
6. DISTRIBUTION.md 与 README 索引行状态过期（写"待平台凭据联调"，实况 = R1.1 排期挂起 09-16）。
7. DECISION_MATRIX "现状"列大面积过期（"失败不扣费 待做"等——ADR-055 已落地）。

---

## A. Docs Census（全 27 份 + 2 目录）

| 文档 | 当前KB | 处置 | 目标KB | 一句话依据 |
|---|---|---|---|---|
| README.md | 11.4 | **KEEP** | 11.4 | 治理表本身健康（09-16 金字塔）；补 research/ "不进默认 context" 一句 |
| PROGRESS.md | 320.8 | **SHRINK（大手术）** | ~60 | 80% 是已完成历史；归档机制从未执行；入口已断链需先滚动 §0 |
| DECISIONS.md | 341.4 | **SHRINK（大手术）** | ~160 | 见 D 节 |
| CHAT_ARCHITECTURE.md | 72.7 | **SHRINK** | ~43 | 考古以括号插句寄生在规则行内，需行级外科手术；文内双源 4 处 |
| NAMING.md | 59.7 | **SHRINK** | ~38 | 宪法+词汇表保留；判例库 44 条中 ~25 条一次性机械更名可删（23.5→8KB） |
| RECIPES.md | 47.7 | **SHRINK** | ~29 | R1/R2/R6 已落地的 dated 修订链压成现状一句话；R3–R5 施工依据保留 |
| PRD.md | 40.1 | **SHRINK** | ~26 | §10 流程（最旧版，引用已退役 `?overlay`）删为指针；留 FR 目录/ICP/规格三件套 |
| MODULE_ARCHITECTURE.md | 34.8 | **SHRINK** | ~23 | §1 整节是 TARGET 却住"现状事实源"（违反五态纪律）；§4 复述 BILLING 三表（违反只引用）；§7.2 日期考古 40% |
| API.md | 34.1 | **KEEP（轻 SHRINK）** | ~30 | 与路由高度同步（20+ 抽查全中）；wallet 面降级为指 BILLING 的指针；修章节号 |
| RENDERING.md | 32.1 | **KEEP（轻 SHRINK）** | ~30 | 契约单源化已完成且抽查全中；§8 过会史移 tasks/done |
| INTENT_COVERAGE.md | 31.5 | **SHRINK** | ~22 | 矩阵本体是全仓最健康大表（抽查全中）别动；删顶部 4KB changelog + 已修划线段 |
| DISTRIBUTION.md | 27.4 | **SHRINK + 刷状态** | ~22 | §11 已取消方案全文删；头部/README 状态改"代码就绪，R1.1 挂起" |
| COMPETITIVE_ANALYSIS.md | 26.0 | **KEEP + 刷新债** | 26 | 三层结构健康；事实停在 07-19 而竞品周级发版——挂"Round 3 刷新"进需求池，现在不动 |
| AGENT_ARCHITECTURE.md | 25.9 | **KEEP（SHRINK）** | ~19 | §2.5 行业坐标保留削调研史；修 S1–S12 陈旧；与 DIALOG/NORTH_STAR 的三方复述收敛为引用 |
| ARCHITECTURE_NORTH_STAR.md | 22.8 | **KEEP（轻 SHRINK）** | ~18 | 五态纪律执行最好；§8.1 六条"已修"叙述可压；§12 文档地图删（与 README 重复） |
| STRATEGY.md | 18.7 | **KEEP（轻 SHRINK）** | ~16 | §5 施工细节引 RECIPES；§7 已兑现行删 |
| DECISION_MATRIX.md | 16.9 | **KEEP + 刷现状列** | 17 | 决策列不动；"现状"列一次性对齐 ADR/PROGRESS |
| DIALOG_WORKFLOW.md | 16.1 | **SHRINK** | ~11 | §7 落地切分表全 ✅（纯历史）、§8 悬案大多已关闭、改名批叙述删 |
| BILLING.md | 15.5 | **KEEP（轻 SHRINK）** | ~13 | SoT 地位成立、抽查全中；孤儿 hold 施工史收 tasks/done |
| MUSIC_ARCHITECTURE.md | 14.2 | **SHRINK** | ~8 | 自称"已实现"但 1/3 是 future（上传/DMCA/Open Questions）——外移需求池 |
| VIDEO_EDITOR.md | 11.1 | **SHRINK 或 MERGE 残部→RENDERING** | ~5 | 契约迁出后只剩 L 分层纪律+交互形态；§10 阶段史归档 |
| POSITIONING.md | 9.3 | **KEEP + PLANNED 闸** | 9.3 | 文档不旧，但必须显式标 PLANNED 并从默认阅读清单隔离（防按目标架构写现状代码） |
| JOURNEYS.md | 8.7 | **KEEP** | 8.7 | 与 DIALOG 是有意分层（用户侧 vs 系统侧），边界健康 |
| LANDING.md | 7.6 | **SHRINK** | ~5 | §4.1 施工日志删（与落地页叙事无关的画布改动记录） |
| MENTIONS.md | 6.0 | **KEEP** | 6 | 健康 |
| REPORT-2026-09.md | 5.5 | **ARCHIVE** | 0 | 09-01 快照已过期，自带"过期即归档"条款；继任者 = 根目录 a.md 草稿 |
| DATABASE_MIGRATIONS.md | 4.9 | **KEEP 原样** | 4.9 | 无时间性 how-to，零赘肉 |
| research/ | 172 | **REFERENCE-ONLY（不瘦不归档）** | 172 | 证据链地基；README 补"默认 context 不加载" |
| tasks/（活跃位） | ~30 份 | **SHRINK** | ~8 份 | b1~b4（README 明说 09-04 收口）等 ~23 份移 done/ |
| tasks/done/ | ~350KB | **移出 docs/ → archive/tasks-done/** | 0（出域） | 与活跃文档同域会被 glob/grep 吸进 context |

---

## B. Duplication Map（12 处，按严重度排）

| # | 主题 | 现在的家（全部） | 合法家（按 README 治理表） | 处置 |
|---|---|---|---|---|
| 1 | 厚 agent 判词 / 有界 loop 两座位 / 常备否决清单 | DIALOG §2.1/§6 + AGENT_ARCH §4.6/§5.4 + NORTH_STAR §3.4/§6/§11 | DIALOG（概念层） | 另两处各留一行指针 + 保留各自特有的工程/目标态内容 |
| 2 | 词汇表 | NAMING 词汇表 + DIALOG §3 canonical 表 + NORTH_STAR §2/§2.1 词典 | NAMING | DIALOG §3 保留"业界出处"列的独特价值，映射行指 NAMING；NORTH_STAR §2 是存在性表（功能不同，保留但删映射重复行） |
| 3 | 文档地图 | README 信息类型表 + NORTH_STAR §12 | README | NORTH_STAR §12 删，留一行指针 |
| 4 | wallet API 面 | BILLING §7 + API.md §11.5 | BILLING | API.md 改指针 |
| 5 | 用户流程 | PRD §10（最旧，引用已退役 ?overlay）+ DIALOG（系统侧）+ JOURNEYS（用户侧） | DIALOG + JOURNEYS 双分层 | PRD §10 删为指针 |
| 6 | 剧本测试清单/数量 | AGENT_ARCH §10 + NORTH_STAR §1 + PROGRESS §0（三个说法全错） | 代码即事实 | 三处统一为"见 chat_scenarios.py"，不写死编号 |
| 7 | 队列机制日期考古 | MODULE_ARCH §7.2（40% 考古）+ ADR-050 取证史 | MODULE_ARCH（机制）+ DECISIONS（决策） | §7.2 删日期留机制；ADR-050 删 pageinspect 取证 |
| 8 | 行业词汇对照 | MODULE_ARCH §4.1 + AGENT_ARCH §2.5 | AGENT_ARCH §2.5 | §4.1 整节移交/删除 |
| 9 | CHAT_ARCH 文内双源 | run 判决 §8.7↔§10；§7↔MENTIONS；§9↔Operation Model；"配方不是 mention" 文内两次 | 各归其家 | 文内合并 |
| 10 | 定位/定位段 | PRD §2 + CLAUDE.md Product Positioning + STRATEGY + POSITIONING | CLAUDE.md（默认层）+ STRATEGY（论证）+ POSITIONING（目标态） | PRD §2 压为一句+指针 |
| 11 | 配方命名登记 | RECIPES §9.5 + NAMING 词汇表 | NAMING | RECIPES 删清单留指针 |
| 12 | NAMING 判例"依据"列 | 复述 DECISIONS 的 ADR 论证原文 | DECISIONS | 判例只留裁决+指向 ADR 编号 |

---

## C. 目标 Active Docs Tree

**不动 README 金字塔分类**——它是对的。要动的是物理结构：新建 `archive/`，把"名义已历史、物理未搬走"的全部搬走。

```
docs/
├── README.md                    # 入口 + 治理表（唯一文档地图）
├── PROGRESS.md                  # 活跃快照：§0 + 未来排期 + OPEN 需求池（~60KB）
├── STRATEGY.md  PRD.md  JOURNEYS.md  LANDING.md
├── POSITIONING.md               # 头部加显式 PLANNED 闸
├── ARCHITECTURE_NORTH_STAR.md  MODULE_ARCHITECTURE.md
├── AGENT_ARCHITECTURE.md  DIALOG_WORKFLOW.md  CHAT_ARCHITECTURE.md
├── DECISIONS.md                 # 68 条现行 ADR（~160KB）
├── NAMING.md  MENTIONS.md  RECIPES.md  INTENT_COVERAGE.md
├── RENDERING.md  VIDEO_EDITOR.md  MUSIC_ARCHITECTURE.md  BILLING.md  DISTRIBUTION.md
├── API.md  DATABASE_MIGRATIONS.md
├── COMPETITIVE_ANALYSIS.md  DECISION_MATRIX.md
├── research/                    # REFERENCE-ONLY（不进默认 context）
├── tasks/                       # 仅活跃施工合同（~8 份）
└── archive/                     # 新建
    ├── PROGRESS-2026-cycle1.md  # §1.3 交付日志 + W1~W7 周报 + 已完成插入批
    ├── REPORT-2026-09.md
    └── tasks-done/              # 现 tasks/done/ 24+23 份整体迁入
```

**新 coding agent 最短阅读路径**（与现状入口一致，只是各环节变短且不再踩雷）：

```
README（金字塔定位）
 → PROGRESS §0（当前 batch）
 → tasks/r1-*.md（施工合同）
 → [动架构时] NORTH_STAR 五态表 → MODULE_ARCH
 → [动对应域] 域文档一份
 → [只读相关条目] DECISIONS
```

---

## D. ADR Slimming Report

### 分类汇总（78 条现行条目）

| 分类 | 条数 | 条目 |
|---|---|---|
| KEEP | 25 | 007, 016, 026, 031, 059, 060, 061, 062, 064~070, 073, 075, 078~085 |
| SHRINK | 43 | 004, 013, 015, 017, 018, 020, 023, 024, 025, 027~030, 032~036, 039~046, 047, 048, 050~058, 063, 071, 072, 074, 076, 077 |
| MERGE | 2 | 001→018；049→047（并入后删条目） |
| DELETE | 8 | 002, 003, 005, 006, 010, 012, 037, 038 |

**数量：78 → 68 条。体积：341KB → 估计 150~170KB（-50~56%）。**

### DELETE 8 条的性质（全是"决策已退化为事实/迁移日志"）

- 002 FastAPI / 005 uv / 006 TanStack / 010 PostgreSQL —— 技术栈事实描述，归 README 技术栈节（其实 CLAUDE.md 已有）
- 003 MiniMax M3 —— 存活规则一句并入 ADR-025
- 012 P0 内部工具 —— "不做计费"已被 ADR-055 实质推翻；定位叙述归 STRATEGY
- 037/038 Speaker→Persona / 人设吸收 Brand —— 迁移已完成（代码实证：brand-template 路由已是 10 行 redirect stub）；词汇规则归 NAMING，schema 归 MODULE_ARCH

### "已翻案但未删"硬证据清单（就地删除依据）

1. ADR-049 整条（删除清单已执行完毕，代码零残留）→ 残句并入 047
2. ADR-051 §3（→053）、§7/§8（→056）、§2 后半（→057/058）——条目内半数文字描述已不存在的形态
3. ADR-047 §5 钩子闸原条款（→049）
4. ADR-063 K5（070 收窄）与"1750px 巨卡"（067 翻案）
5. ADR-046 附⑯⑱（048 迁移）与被再调取代的点阵旧值
6. ADR-057 §5 端口法则两次修订细节（现行形态由 067/068 承载）
7. ADR-050 的 120s 首日翻案史（只留"600s、部署必配"）
8. ADR-036 D1/D3 自标翻案入 057 但正文全文在；补记 2 前置核查已动工
9. ADR-041 D5 补丁族火化段、D8 focus 退役段（带删除线但未删）
10. ADR-012 未标注已被 055 推翻
11. ADR-004 被 025 修订的 rationale 仍挂
12. ADR-034 被 077 修订但未挂修订注

### 压缩格式（KEEP/SHRINK 统一为）

```
## ADR-0xx: 标题
Status: Accepted（或 Pending / Amended-by-ADR-0yy）
Decision: …（编号判词本体）
Why: 一段
Constraints: - …
Non-goals:（必要时）
```

删除：会议过程 / 候选方案长文 / 取证史 / 批次史 / commit hash 考古 / 同日多轮翻案叙述（全在 git）。
**保留例外**：负向约束（"永禁 X"）即使源自翻案也保留结论句——它们住 DECISIONS 或各文档禁令节，考古叙述删、禁令本身不删。

### 施工注意（来自三区间报告的形态观察）

- **ADR 文体在 059 处自发转向**：046~058 是"长考据+同日翻案"文体（历史占 40~60%），059 之后已是短条目规则文体——压缩工作量 80% 集中在 046/048/050/051/052/055/057 + 071/072/074/077 约 11 条。
- 物理行数是假象（一 bullet 一行，单行最长 1.5K 字符），瘦身按字符衡量。
- CHAT_ARCH / MODULE_ARCH 的考古是**括号插句寄生在规则行内**，需行级外科手术，不能整行删。
- 顺手修 drift（不属于瘦身但同批做成本低）：ADR-025 接口名对齐代码、ADR-042 标 Status: Pending、三处剧本编号改指针、API.md 章节号、MODULE_ARCH clients/ 行。

---

## E. 建议施工顺序（每批 commit 级自绿）

1. **批 1（纯搬运，零内容风险）**：建 `docs/archive/`；移 tasks/done/ → archive/tasks-done/；移 REPORT-2026-09；tasks/ 活跃位清扫（~23 份已完工简报入 archive）；README 同步。**-355KB，不动一字正文。**
2. **批 2（PROGRESS 大手术）**：先滚动 §0 修入口断链（R1 封板后的下一步拍板）→ §1.3 + 已完成周/批 整体切出到 archive/PROGRESS-2026-cycle1.md → 需求池死条目关闭。**-255KB。**
3. **批 3（DECISIONS）**：DELETE 8 + MERGE 2 → 翻案残文 12 处就地删 → SHRINK 43 条按格式压缩 → 同批修 ADR-025/042/034 drift。**-170~190KB。**
4. **批 4（架构五件套）**：CHAT_ARCH 行级外科手术 → MODULE_ARCH 删 §1/§4 复述/§7.2 考古 → DIALOG 删 §7/§8 历史 → AGENT_ARCH/NORTH_STAR 轻修 → 三处复述收敛为指针。
5. **批 5（域文档）**：PRD/RECIPES/NAMING/INTENT/DISTRIBUTION/MUSIC/VIDEO_EDITOR/LANDING 各自压缩 + 状态刷新。
6. **批 6（治理收口）**：README 补 archive 规则 + research/ REFERENCE-ONLY 条款；DECISION_MATRIX 现状列刷新；竞品 Round 3 刷新债挂需求池。

验证纪律：每批后用户自跑（grep 关键约束词确认未误删 / 文档链接检查）；正文压缩批先用 git diff 过一遍"删的都是叙述不是规则"。
