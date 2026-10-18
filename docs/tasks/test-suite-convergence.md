# 测试体系收敛：主流程矩阵 + 机制不立锁

> Status: 已拍板待开工（ADR-114，2026-10-10 用户拍板：四组退役名单过堂全数通过）
> 施工合同。开工先通读本文 + ADR-114；排期归 `PROGRESS.md`，本文只管怎么施工。

## 1. 背景与判词

六代理全层审计（2026-10-10）实测锚点：剧本 41 本 / 纯 pytest 51 本 918 例 / vitest 11 本 / check_gates 8 门 / prompt_gate 12 探针 / scripts 仪器 24 件。淤积集中在「为某次拍的锁」（剧本层 31 本、scripts 一次性仪器、文档漂移四处）；钉现行法的层（纯 pytest / vitest）天然健康。

用户判词：不要过度设计，降低心智负担；高速迭代期很多东西都会过时；无需保留为某次而针对的测试内容；始终需要的主流程测试 = 各种类型的用户通过 chat 进行的各种类型的创作流程。

三批顺序：批 1 删除批（小）→ 批 2 剧本矩阵（大手术）→ 批 3 文档座位批。一批一 commit 族，per-commit 自绿。

## 2. 批 1 — 删除批

### 2.1 删除（git 历史即档案，不留注释尸体）

- `apps/api/tests/` 六本：
  - `test_repair_visibility_pure.py` — `on_repair` 死槽（消费接线 44b5d4d 已删）
  - `test_wire_tiers_pure.py` — `pick_wire_tier` 零调用且与 loud-failure 现役律矛盾（假绿）
  - `test_frame_aspect_pure.py` — 私有镜像锁（事故根修出生）
  - `test_material_wait_pure.py` — 负空间锁（锁一个已删键不回来）
  - `test_output_delete_pure.py` — 语句顺序锁（实现形态镜像）
  - `test_autofork_pure.py` — 演示事故出生
  - ⚠️ `test_check_gates_pure.py` **不删**（闸接线后它是唯一看守 5a/5b/5c 牙口正则的座）
- `apps/web/src/lib/utils.test.ts` — 两条断言测 clsx/tailwind-merge 第三方库自身行为
- `apps/api/scripts/` 六件：
  - `spike_reframe.py` — ADR-045 一次性前置闸，硬编码仓库外文件，产物已内化
  - `reframe_smoke.py` — 依赖仓库外文件 + /tmp 易失缓存，重启断链
  - `track_model_fixture.py` — 一次性验收 fixture，无注册座
  - `accept_prompt_surface.py` — 验收轴已被顺形律批翻案（模板不再点名工具形态）；自红一个月
  - `migrate_to_tos.py` — 一次性迁移（verification-overhaul 已挂账）
  - `backfill_graph.py` — 一次性回填（⚠️ 工作树有未提交维护 diff，删除即 supersede，已拍板）
  - `migrate_activity_log_rows.py` **不删**（生产未跑完；CHAT_ARCHITECTURE 引用它）

### 2.2 修改

- `apps/api/scripts/check_gates.py`：
  - 删 Gate 2（`parallel_maps` 整门——只咬退役旧名，新名字同类违规看不见）
  - 删 Gate 4 的非 checkpoint 条款（`SkillEntry`/`SkillRejected`/`dispatchable_skills`/`app.clients`/`app.agents.roster`/`roster.py`）；**保留 `kind="checkpoint"` 字符串条款**（ADR-085 reclaim 后是活牙）
  - 门编号留洞不重排（verification-contracts / test_check_gates_pure 的引用保持有效）；docstring 头部同步为现在时
- `apps/api/scripts/prompt_gate.py`：
  - 删 PROBE_H2 / PROBE_H3（定义 + 注册表项 + docstring 头部枚举同步）
  - PROBE_G 补 `edit_output` never 负形子句（与 H 族对称，升格为开放 craft 修订代表）
  - PROBE_I 保留；docstring 标注「阈值未校准——首次定带跑后按读数校准，校准跑归用户」
- `apps/api/tests/test_exploration_tools_pure.py`：修 `test_family_is_not_in_the_production_turn_tools` 假绿断言——前提已过时（`plan_turn.py` 已在生产分发探索族），改为锁现行真实形态或删该例

### 2.3 引用同步（随批）

- `docs/tasks/output-display-unification.md` 的 accept_prompt_surface 验收命令引用删除/改述
- `docs/DECISIONS.md` 中 migrate_to_tos 的行级引用顺手删
- `docs/tasks/verification-contracts.md` 里被删文件的 KEEP 名单行顺手删（全文重写归批 3）

## 3. 批 2 — 剧本矩阵（大手术）

**开工硬前提（2026-10-11 批 1 验证取证后立）**：在途批（ADR-111/112 + transcript-fold）落地且分水岭验证全绿后才开工——取证实证 tests/ 与在途批终态对齐（`graph_wiring_pure` / `product_graph_pure` 两本 collection 崩 = 退役符号 `stamp_transcript_node` / `effective_rank_edges` 上的 ~400 行用例，归在途批落地时处置；HEAD 既有红 10 处的被测对象全部在在途批修改清单里），在途未落地前 pytest 面红无法归因。分水岭验证含 prompt_gate 全量 10 探针（在途批改了 turn_tools 措辞面，测移动靶无意义）。

`apps/api/scripts/chat_scenarios.py` 重写：**41 本 → 10 本用户旅程矩阵**，编号连续重排 S1–S10（旧 S 号全部作废，第二次）。保持单文件（拆文件/搬家是 verification-overhaul P3 的事，不在本批）。

### 3.1 矩阵（每本 = 一种用户 × 一种创作流 × 全旅程）

| # | 旅程 | 内容要点 | 断言继承自 |
|---|---|---|---|
| S1 | 迷失用户全旅程 | 裸愿望 → 主题问 → 作答（自由文本 + 选项点选两路）/ 跳过 → draft-from-persona 计划 → dock → 口头确认 → start_run → run | 旧 S1 + S2 + S-int-3 |
| S2 | 素材→短片全链 | 上传视频 → clips 计划 → 确认 → run completed + 产物落库 → **途中插话**（代码拼装提醒尾 + pending 保持 + 下轮回填）→ chat 修订 wiring 横切（同 id 原地改写无双生 → 子图重跑） | 旧 S4 + S5 + S3 |
| S3 | 素材→建议→探索 | 上传素材问建议 → propose_candidates → selects → plans → 决策包 dock（plans + 编译链 + quote）→ Start → confirmed_scope 快照 → 产物落地 | 旧 S23 + S-explore-2 + S-int-2 |
| S4 | 无素材→图文 | 写手族（post / quotes / carousel）无素材直生 + caption_mode 默认吸收（选项问 → 回执 + run.context） | 旧 S7 + S-int-8 |
| S5 | 调研→写作 | research 全链（活 DDG；网络全灭时 caveat 降级也算过） | 旧 S8 |
| S6 | 纯咨询不死路 | 能力问 / 浏览问 → 纯 answer 终态，零计划零 dock 零 run（形态断言，永不锁措辞；旧 lane 历史不劫持新政策） | 旧 S9 + S-int-1 + S-int-5 |
| S7 | 修订第二圈 | 落地 clip → 精确编辑（remove_range / set_trim / set_title / set_caption_style 四族至少跑两族）→ 同 id 无双生 + 归档生命周期 | 旧 S-edit |
| S8 | 访谈→分镜 | 访谈 fixture 真处理 → 口头选定分镜方向 → 链必含 select_clips + reframe_clip → run completed → render_spec 带 crop_track | 旧 S24 |
| S9 | 付费边界 | 余额不足 → typed Start 与 /generate 双路 422 同形同义 | 旧 S13 |
| S10 | Remix 旗舰 | 配方卡预填 → 对话定计划 → 生成 → 结果 → 下一步 | 旧 S16 |

点名工作直达 present_plan 的形态（旧 S-int-4）并入 S2 入口变体断言。

### 3.2 harness 公共断言（每本自动携带，不再单独立本）

- SSE 工具 loop 线格式：`concat(deltas) == 信封散文`；读先 startswith 前缀律；拒轮方差注记
- Activity 帧形态（composing 唯一相位座）+ question.preview 预览帧
- dock 三形态机
- 估价三断言：flow 对账自检过 / 报价单调性（子图 ≤ 全图，非负）/ repair 只一轮
- 形态级断言纪律不变：永不锁 LLM 文案（提醒尾 / 机器标记 / 确定性回执等代码强制文本例外）

### 3.3 下沉 `tests/`（进程内纯函数，不占矩阵）

- 旧 S11 的 materialize 注入矩阵、旧 S12 的 merge_brief 来源矩阵、旧 S25 的 transcript 数组序
- 优先进既有同族文件（`test_brief_pure` / `test_transcript_cues_pure` 等），无同族再开新文件

### 3.4 删除的 31 本

旧 S6 / S14 / S15 / S17 / S18 / S19 / S-wait-1 / S-wait-2 / S20 / S21 / S22 + S-int-9（迁移期锁，lane 已退役）+ S-int-10/11/12/13/14（事故锁）+ 被合并的源本（旧 S1/S2/S3/S4/S5/S7/S8/S9/S13/S16/S23/S24/S-edit/S-explore-2/S-int-1/2/3/5/8 以新形态存活）。

### 3.5 故意放弃的覆盖（用户知情拍板，ADR-114 Consequences 在案）

失败不扣费（旧 S14）/ 孤儿 hold 回收（旧 S15）/ run 执行权仲裁（旧 S17）/ turn durability（旧 S19）/ SSE 断流复连（旧 S-int-14）/ repair 静默与泄漏锁（旧 S-int-12/13）。

### 3.6 flake 处置

旧方差族（S1/S6f/S10）经验随 harness 继承：断言只锁形态；红先归因机制（pre-批面复跑分水岭纪律），**禁调断言放行**。矩阵内任何本连续两次同类方差红 → 登记 PROGRESS 需求池，不静默。

## 4. 批 3 — 文档座位批

前置：批 1/2 已合入（文档描述批后现实）。

**两波施工（2026-10-11 平行会话避让）**：3a = 与活跃批次零纠缠的七座（CLAUDE.md / AGENT_ARCHITECTURE / BILLING / DIALOG_WORKFLOW / verification-contracts / verification-overhaul §2 / material-wait-in-turn）；3b = DECISIONS.md / PROGRESS.md / CHAT_ARCHITECTURE.md 三座，等在途 ADR-115 批落 main 后开工（它在三座上有活跃改动，同改即漂移坑）。`interaction-architecture.md:68` 的 test_wire_tiers 叙事提及移出本批——归 ADR-099 活跃批自清。

- `CLAUDE.md` Testing 节（:186–194）**重写为新哲学之家**：
  - 两层保留（主流程矩阵 + 承重守卫）一句话
  - 部署前仪式链：纯 pytest → **check_gates（接线——本决策把它从僵尸仪式变真闸）** → prompt_gate（动 prompt 面时；探针数修正为 10）→ 剧本矩阵 S1–S10
  - 仪表层登记（非闸）：reply_quality_probe / accept_quote_card_family / reconcile_credits / verify_beat_map / crop_track_parity / run_anatomy_matrix / craft_anatomy
  - vitest 10 本；router_ab_probe 死链删除
- `docs/AGENT_ARCHITECTURE.md` §10（:226）改写：验收器 = 两类清单 + 矩阵指
- `docs/CHAT_ARCHITECTURE.md` :105（S1/S2 → 新 S1）；:245/:250 措辞顺手
- `docs/BILLING.md` :154（S15 引用删除/改述）
- `docs/DIALOG_WORKFLOW.md` :3（S50~S53 死引用删除）
- `docs/PROGRESS.md` §0.4 规则 5/8 随 CLAUDE.md 同步
- `docs/DECISIONS.md`：
  - ADR-071 改写：router_ab_probe 死链删 / 「三探针」计数修正 / 部署前仪式链更新
  - ADR-099 两条 golden suite 义务改写（旧腔调风险覆盖 = 矩阵 S6 + prompt_gate I）
  - ADR-084/085/093/104/109 的 S20/S21 回归座句删除或改指（打字机律承重座 = paceSettledProse + vitest 层）
  - ADR-039（S1–S40 计数删）/ ADR-040（「S22 留空不回收」句删）/ ADR-089（「全量剧本」改指矩阵）/ ADR-064（S12 引用改指下沉后 tests 座）/ ADR-090 / ADR-094（剧本座改指新编号）
- `docs/tasks/verification-contracts.md` 重写：保留「合同 ↔ 承重守卫映射」；删 §4 方差台账（S 号为键全灭）/ §5 fixture 硬化清单 / §6 批次考古；fixture 律与方差经验移入本文 §3.6/§5
- `docs/INTENT_COVERAGE.md` **不动**（README 已登记 retired，retired 文档不维护）
- 批 1 收官挂账三处（死引用清理）：
  - `docs/tasks/material-wait-in-turn.md` :63 — 引用已删的 `test_material_wait_pure.py`，改述或删行
  - `docs/tasks/verification-overhaul.md` §2 普查表 — 三族分家清单仍列六件已删仪器，同步为删后现实（Status 行已先行更新）
  - ~~`docs/tasks/interaction-architecture.md` :68~~ — 移出本批，归 ADR-099 活跃批自清（其迭代二在施工中，不碰活跃批次合同）

## 5. Prohibited Behaviors

- 永不调阈值 / 放松断言让红变绿；prompt_gate 阈值只准按校准跑读数定，禁为放行回归调阈
- 不留注释尸体（注释掉的测试 = 删除）；删就删透
- 剧本永不锁 LLM 文案；客户端法律（typewriter / remount / 形态机）不进剧本断言——服务端真值才进
- **机制不立独立剧本**：新机制的覆盖需求必须能说出「矩阵哪本旅程的哪一步」，说不出归属旅程的覆盖需求先回炉
- 不顺手修与本批无关的失败/缺陷（登记 PROGRESS 需求池）
- 零 schema 变更；零新依赖
- 批 2 禁拆文件 / 搬家（P3 归位是后续独立批）
- fixture 纪律：剧本素材先拷 `scenario/` 前缀（delete_project 会 unlink 外部共享 key）；常驻 worker 抢跑律——手工验证前后清数据，改 pipeline 代码必须重启 worker

## 6. 验证纪律（用户自跑，施工会话只做代码层并标「未跑验证」）

- 批 1 后：纯 pytest 全绿（减 6 本基线）+ vitest 绿 + check_gates 绿（剩 6 门）+ tsc
- 批 2 后：纯 pytest 绿（含下沉三本）+ 剧本矩阵 S1–S10 全量（需活 API + dev worker + MiniMax 配额 + fixture 纪律）+ prompt_gate 全量（10 探针）
- prompt_gate I 探针首次定带跑：跑后按读数校准阈值（独立小 commit）
- 批 3 后：文档零死链——grep `router_ab_probe` / `accept_prompt_surface` / 旧 S 号（S50/S39/S38 等 C4 前编号）零命中

## 7. 验收标准

- 批 1：§2 清单全落地；纯 pytest / vitest / check_gates 绿（用户跑）
- 批 2：S1–S10 矩阵在活 API 全绿（用户跑）；harness 公共断言承载旧 S10 的 SSE 律；下沉三本进 tests/
- 批 3：§4 座位全清；CLAUDE.md Testing 与实测一致
- 全批 conventional commits，per-commit 自绿，文末署名 `Co-Authored-By: Claude Code <noreply@anthropic.com>`
