# R1 Batch 1 — Remix 旗舰旅程收口 + 测试地基复位

> Status: IMPLEMENTED（2026-09-16 施工 + 验证完毕：纯套件 190 绿 / gate 0 注入验证过 / prompt gate 3/3 / S16 剧本绿；Implemented: cd90fca / Verified: 2026-09-16。排期唯一事实源 = `docs/PROGRESS.md` §0.1，本文件只是施工合同）
> **开工纪律**：本文件的文件/行号核验于 HEAD `e8dbced`（2026-09-16）。行号会漂移——开工前以 current HEAD 重新定位代码座位；docs 与 code 冲突时 `Current code > DB constraints/migrations > tests > ADR > 架构文档`。发现本合同与代码不一致 → 标记 discrepancy 回报，不自行扩大 scope。

> **施工记录（验证驱动的范围外修复，单独说明理由）**：
> 1. **`messages.intent` JSON → JSONB（migration `c5a1f7b3d9e2` + 模型列）**——S16 实证：generic JSON 列的 `col["k"].astext` 在本 SQLAlchemy/asyncpg 栈直接 AttributeError，trigger_turn `_already_spoke` 每次必炸，**全部三种触发回合自 T3（09-15）出生起在 dev 全静默**（best-effort 吞异常 + 纯测试 stub 不编译真实 SQL）。不修它 T4 的 DoD「trigger_review 可达」结构性不成立。
> 2. **`get_craft_skeleton` 读工具 FAILED 分支文案**（`perception/executes.py`）——原文案对 FAILED 参考片说「still processing, lands in a moment」，agent 等一个永不落地的骨架、remix 旅程在出书前死锁（S16 实测）。改为告知「处理失败但 run 内 decompile 直读字节，不可读则诚实按常规剪」。
> 3. **既有闸门红两处（未修，非本批引入）**：`app/tools/stills/agents.py:14` 违反 N-29（HEAD 自带的 check_gates 复跑同红，Gate #2 反审的 PASS 未覆盖）+ `propose_turn.py:141` 注释含退役词 `checkpoint`。已回报，归各自批次。
> 4. **已登记 OPEN 发现**：mention pin 只在 PendingPlan 写入时持久化——bare-answer 回合零写入则 pin 蒸发（S16 以有界 re-mention 兜住，产品侧修复待拍）；router 在旗舰句上两次直接出默认 plan 不问角色（prompt 规则在册，miss 率归 prompt 探针，INTENT_COVERAGE §6 ⚠️ 行）；`delete_project` 逐 asset unlink file_url 无前缀守卫（S16 首轮误删配方卡营销片，已从同内容孪生 key 恢复——scenario fixture 现一律拷 `scenario/` 前缀，C1 批需产品侧守卫）。

## 1. Product goal

服务 **J2（Remix 旗舰旅程，`docs/JOURNEYS.md` 旅程二）**。

用户故事：两个视频 + 一句「你能帮我把我的原视频做成案例视频这样子吗？」→ 角色消歧 → agent 主动说看懂了案例 → 产物在**当前支持维度**上明显受参考片影响 → 可继续修改。

为什么是现在：decompiler 五拍（T5①~⑤）机制已全绿，但旗舰旅程**没有任何自动化验收锁住它**，且 run 路径上拆解静默发生、画布上 decompile 落成一个语义错误的孤儿节点。旗舰旅程是产品差异化门面，不能裸奔。

## 2. Current state（核验于 e8dbced）

- decompile 节点全链已在：`apps/api/app/pipeline/decompile.py`（craft_scan 确定性扫描 + CraftJudgment 三座位 + CraftSkeleton 内部产物 + 内容寻址复用）。
- warm 路径物化后**会**发触发回合：`decompile.py:357` `fire_trigger(project_id, TRIGGER_CRAFT_DECOMPILED, ...)`。
- **run 路径物化不发触发回合**：`decompile.py` `Decompile.run()`（:435-509）新鲜物化后无 `fire_trigger`——用户在 remix run 里听不到「我看了你的案例」。
- 画布 seam：`Decompile` 类（:381-391）只声明 kind/task_name/agents，无 `node_type/prototype`；`_decl_of` 落默认 **text×manual**（`app/pipeline/graph_fill.py:152-153`），且 `decompile` 不在 `_PRELUDE_KINDS`（`graph_fill.py:71`，其成员 = preprocess/persona_bootstrap/understand/interrupt/plan）→ 画布上多一个语义错误的独立节点。其自述「与 understand 平行」，而 understand 在 prelude 里。
- exemplar 参数消费（确定性，ADR-078 判词⑤）：count `app/tools/clips/node.py:225` / aspect `:325` / captions `:341` / music `:368`。
- 测试漂移 4 个（实测 `uv run --extra dev python -m pytest tests/ -q` = **4 failed, 186 passed**）：
  1. `tests/test_decompile_pure.py::test_chat_path_role_pins_inherit_mention_wins_reversal` — stub `SimpleNamespace` 缺 `project_id`（实现 `app/chat/propose_turn.py:183` 读 `asset.project_id`，stub 没跟上）；
  2. `tests/test_prompt_registry_consistency_pure.py::TestEnumeratedNamesAreRegistered::test_all_enumerated_tools_exist` — prompt 枚举行了未注册工具（caption 相关）；
  3. `tests/test_tool_loop_pure.py::test_unknown_tool_and_bad_params_are_feedback_iterations` — echo 期望漂移；
  4. `tests/test_tool_loop_pure.py::test_declaration_guards` — DID NOT RAISE。
- 无 import smoke gate：`apps/api/scripts/check_gates.py` 只查架构闸门；boot 崩溃（T5① 前向引用，已由 `1dc3c88` 修复）曾让全套件在 collection 即死、五个 commit 无人察觉。
- remix e2e 空白：`apps/api/scripts/chat_scenarios.py` 全文 grep decompile/remix/craft/exemplar = 0 命中。

## 3. Gap

旗舰旅程四件事：① 零自动化验收；② run 路径拆解静默；③ 画布孤儿节点；④ 测试地基（4 漂移 + 无 gate 0）让前三个的验收无处立足。

## 4. Files / modules

- `apps/api/tests/test_decompile_pure.py` / `test_prompt_registry_consistency_pure.py` / `test_tool_loop_pure.py`
- `apps/api/scripts/check_gates.py`（gate 0）
- `apps/api/app/pipeline/graph_fill.py`（`_PRELUDE_KINDS`）
- `apps/api/app/pipeline/decompile.py`（run 路径触发）
- `apps/api/scripts/chat_scenarios.py`（remix 剧本）
- 文档：`docs/JOURNEYS.md` / `docs/PROGRESS.md`（状态同步）

## 5. Preconditions

无前置 batch。R1 首批。

## 6. Implementation tasks

### T1 — 4 个测试漂移复位
- **Objective**：纯函数套件全绿，且每个漂移先判定「测试对还是实现对」。
- **Seat**：上列 4 个测试文件。
- **Expected behavior**：逐案处理——stub 补齐实现已读的字段（对齐实现的读取面，不是改实现迁就 stub）；prompt 枚举与注册表不一致时先查哪边是真相（注册表 = 启动对账的一方通常是真相，prompt 枚举漏注册 = 改 prompt；**VERIFY BEFORE CODING**：caption 工具是否已拍板注册）。实现侧确需改动的，单独说明理由。
- **Tests**：4 个失败转绿；**禁止为绿而改断言**，除非证实该断言落后于已拍板行为（引用拍板出处）。

### T2 — import smoke 入 check_gates.py（gate 0）
- **Objective**：「全模块不可导入」从 pytest collection 崩溃变成显式闸门失败。
- **Seat**：`apps/api/scripts/check_gates.py` 顶部，子进程 `import app.main`，失败即非零退出并标明这是 boot 级失败。
- **Tests**：手动注入一次 import 错误验证 gate 0 报警（验证后回滚）。

### T3 — decompile 入 prelude（画布孤儿修复）
- **Objective**：decompile 步骤折进 prelude 家族，不再生成独立画布节点。
- **Seat**：`app/pipeline/graph_fill.py:71` `_PRELUDE_KINDS` 加 `"decompile"`（与 understand 同待遇——其类 docstring 自述「与 understand 平行」）。
- **Expected behavior**：remix run 的画布无 decompile 孤儿节点；plan 节点 steps 含 decompile；既有 `test_graph_wiring_pure.py` 不红。
- **Tests**：纯套件 + remix 剧本（T5）画布断言。

### T4 — run 路径 craft 触发回合
- **Objective**：run 路径新鲜物化与 warm 路径同权发声。
- **Seat**：`decompile.py` `Decompile.run()` 新鲜物化尾（`_row(...)` + summary 之后，现 :484-509 区域）补 `fire_trigger(project_id, TRIGGER_CRAFT_DECOMPILED, str(asset_id))`。
- **Expected behavior**：新鲜物化 → 触发回合可达（`trigger_turn.py` 白名单已含 `TRIGGER_CRAFT_DECOMPILED`，无需改）；**复用命中（:468-470）不新发**。已知边界（登记，不修）：跨项目复用时本项目的会话可能从未听过案例理解——`_already_spoke` 按 (conversation, trigger, ref) 去重，是否补「本项目首见即发声」属产品小决策，标记 **OPEN**，本批不实现。
- **Tests**：remix 剧本断言 run 路径拆解后产生 `trigger_review` 消息。

### T5 — remix e2e 剧本
- **Objective**：旗舰旅程有自动化验收。
- **Seat**：`apps/api/scripts/chat_scenarios.py` 新增场景（归 INTENT_COVERAGE §6 登记）。
- **Expected behavior**：两个视频 + 一句「做成案例那样子」→ 资产角色消歧（提问机器或 @mention pin）→ decompile 节点执行 → run.context/产物体现 exemplar 参数（count 档位 / aspect / caption preset / music mood 至少可断言之二）→ 产物落库 → 触发回合消息存在。fixture = demo 桶固定参考片（需烘焙一条特征明显的参考片：已知条数/画幅/字幕 preset——**VERIFY BEFORE CODING**：demo 桶现有素材哪条可作 fixture，必要时新烘）。
- **Tests**：剧本绿（用户自跑，需 dev worker）。

### T6 — 文档同步
- JOURNEYS 旅程二相关拍位与缺口表状态翻新（若落档批未先做）；PROGRESS §0.1 本批翻 DONE + commit 号；INTENT_COVERAGE §6 登记新剧本。

## 7. Do NOT touch

- 结构级 remix / 骨架时序结构消费（产品承诺未拍板，OPEN）。
- Media IR / artifact lineage / cache identity（归 R1.1 并行批 C1）。
- `_find_reusable_skeleton` 的 latest-20 扫描与索引化（C1 范围，本批**不许顺手改**）。
- op 覆盖度扩面（字幕 size/color）。
- B4 镜头跟随。
- 跨项目复用发声（T4 的 OPEN 项）。

## 8. Acceptance

**Mechanism DoD**：
- [ ] `cd apps/api && uv run --extra dev python -m pytest tests/ -q` 全绿（含原 4 个失败）
- [ ] `uv run python scripts/check_gates.py` gate 0 在位且全闸门过
- [ ] remix e2e 剧本绿（用户自跑）
- [ ] run 路径拆解 → `trigger_review` 消息可达；复用不重复发声
- [ ] 画布无 decompile 孤儿节点

**Product DoD（人工验收脚本，用户自跑）**：固定参考片 + 一条用户素材 + 一句「做成案例那样子」，全程无需理解 decompile/skeleton/exemplar 概念，逐行打勾：

| # | 维度 | 通过标准 |
|---|---|---|
| 1 | agent 的理解陈述 | 触发回合说出的案例理解（条数/节奏/字幕/画幅）与参考片事实相符 |
| 2 | 条数 | 产物条数 = 参考片档位 |
| 3 | 画幅 | 产物画幅 = 参考片画幅 |
| 4 | 字幕样式 | preset/颜色可辨地接近参考片 |
| 5 | 配乐氛围 | mood 与参考片节奏同族 |

> 该脚本同时是未来「结构级 remix 是否产品承诺」拍板的测量仪器——参数级仿制「像不像」的证据由它持续产出。

## 9. Docs update（完成后同批）

- `docs/PROGRESS.md` §0.1：B1 → DONE + commit。
- `docs/JOURNEYS.md`：旅程二拍 1/拍 3 状态、缺口登记表。
- `docs/INTENT_COVERAGE.md` §6：remix 剧本行。
- 本文件 Status → DONE（Implemented: <commit> / Verified: <date>）。
