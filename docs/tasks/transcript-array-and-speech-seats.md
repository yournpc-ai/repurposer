# Transcript 数组化 + 言语座位通用化 — 施工合同

> Status: **施工完成待验收（2026-10-07）**。W1 数组地基（`e01f7b9` seq + 计数器表 / `6aea321` 每帧一行 + SSE row 镜像）· W3 前端单渲染路径 + 折叠行（`678e2a2`）· W4 内核（`d5b924b` checkpoint 通用化 + cap 4）+ prompt 面（`cd35491` 相位叙事律 / echo 可见性戒律 / 模式承诺句 + TaskItem.params `''→{}` 读容忍）· W5 迁移脚本（`scripts/migrate_activity_log_rows.py`，dev 库已实证：旧聚合行清零、seq 重编 1..N、计数器对齐、取证母本会话 12bb1f29 物化正确）+ S25 回归座（`scripts/chat_scenarios.py`，行序 / wire 镜像一致 / 回放恒等 / 诚实 transcript 形态锁）+ CHAT_ARCHITECTURE §8.6 排序律→数组位置律改写。**待用户自跑验收**（合同 §5）：prompt_gate 全探针 / chat_scenarios 全量 / 取证母本 live 回放三件套。验收通过后本简报归 `docs/archive/tasks-done/`。
> **candidates_log 结论（W1 论证保留分支）**：保留聚合行，不数组行化。取证：候选卡的消费面 = 单卡数据链（set 出生 + selection 重绘，卡片在原地 repaint，是「面」不是时间线行；chat 决策永不成节点同族）；其数组位偏差（live 中回合中途出生 vs 回放锚在回合末的聚合行位）是一回合内的秒级差，且卡片的回放位置在数组化前后一致（都锚聚合行）——数组化它只会把一张卡拆成多行，收益为零、折叠语义变浑。
> 母法 = `docs/DECISIONS.md` ADR-108（数组化）+ ADR-109（言语座位）；行为律全文 = `docs/CHAT_ARCHITECTURE.md`（§8.6 已随批改写为数组位置律 + checkpoint 通用座位 + 折叠规格）。
> 取证母本 = 项目 `3e333147-35e0-41ea-8c80-828d41c71893`（2026-10-07 live 取证，四事故：活动行消失 / 活动行刷屏 / 开工句顺序错乱 / echo 指向不可见工作空间）。

## 1. Product Goal

消息流 = append-only 类型化数组，持久化顺序即渲染顺序（对标 Claude Code / Codex 会话模型）；言语在工具边界的公共座位上按相位节奏出站。用户可见结果：① 看过的活动行永不消失；② 开工句/相位句永远出现在它该在的位置（读之前）；③ 连续同类活动行折叠为一行；④ echo 永不指向用户看不见的面。

## 2. Current State（核验于 2026-10-07 HEAD，行号会漂移，开工前重新定位）

- 活动行持久化 = 每回合一行聚合消息 `intent.type='activity_log'`（`app/chat/routes.py` `_persist_activity_log` / `app/chat/service.py` `record_activity_log`，once-only per ref 去重），帧在 `app/chat/activity.py` `ActivityProjector` 投影，SSE 经 `assistant.activity` 帧。
- 前端渲染 = 运行时重算交织：`apps/web/src/lib/chatTimeline.ts:78-93`（walk key 混排）、`apps/web/src/components/chat/historyReplay.ts:141-177`（activity_log 解析，last-wins 只演最新回合）、`apps/web/src/components/chat/ChatDock.tsx`（`logDismissed` 闩 ~2441 / `latestLog` ~3672 / `finalizePreview` 重锚 ~2557 / `paceSettledProse` ~2571）。
- checkpoint 通道：`app/agents/tool_loop.py:677-727`（`checkpoint_route` 白名单判定 + `MAX_CHECKPOINTS_PER_TURN=2` ~L127）；资格注册在 `app/chat/perception/__init__.py`（`checkpoint_eligible=True` 仅 `get_understanding`/`get_asset` 两席）；runner 座 `plan_turn.py` / `propose_turn.py` 的 `on_checkpoint_after_flush`；落库 `service.py` `_checkpoint_callback`，SSE `routes.py` 转发携 `created_at`。
- 言语提交协议（ADR-099 §7）：`app/chat/deferred_frames.py`——本批不动。
- `PresentPlanArgs` 校验座位：`tool_loop.py` params_validation 拒绝路径（~L651）。

## 3. Work Items

### W1 — 数组地基：`seq` + activity 行即数组行（服务端写口）

- `messages` 加 `seq`（per-conversation 单调 bigint，Alembic 迁移 + 存量按 `created_at` 回填；新写口单写者分配——chat 回合已序列化，trigger/answer 路径同 writer 纪律）。
- activity 投影器改双写时点：open 时 `row.append`（`at` = execute 入口时刻，即 ADR-104 ReadExecuting 重锚点），settle/failed/cancelled 时 `row.update` 同行（`duration_ms` + 终态）。行形态 = `intent.type='activity'` 单帧行（kind/key/status/at/duration_ms/activity_id）。
- `_persist_activity_log` 聚合行形态退役（删写口；旧数据由 W5 迁移脚本物化）。
- 失败/中止回合：已 append 的 activity/checkpoint 行照常提交（不随回合回滚），终态 failed/cancelled 原地 update。
- candidates_log 同法改造（数组行化）或论证保留——开工时先取证其消费面再定，结论写入简报 Status。

### W2 — SSE 镜像数组操作

- 帧形态收编为 `row.append` / `row.update` / `row.delta` / `row.settle`（可在现有 `assistant.*` 帧族上改造，不必另起事件名——开工时盘点现有帧，能承载就承载）。
- checkpoint / activity / 散文首 delta / candidates 全部走同一数组语义：append 定位置，update 改内容。

### W3 — 前端单渲染路径 + 折叠行

- 历史回放 = `ORDER BY seq` 直渲；`chatTimeline.ts` 的 walk key 混排、`historyReplay.ts` 的 activity_log 解析与 last-wins、ChatDock 的 `logDismissed`/`latestLog`/`finalizePreview` 重锚**整层删除**。
- live SSE 消费与回放共用同一 reducer（数组 append/update/delta 语义）；散文气泡首 delta 到达即占位 append，settle 原地 finalize，位置不动。
- 折叠渲染（呈现层纯函数）：连续同 kind completed activity 行折叠为「已检索转写 ×N · 共 Xs」聚合行，点击展开明细；进行态行不折叠（StatusLine 一座两行律不变）。
- i18n en/zh 双写折叠行文案。

### W4 — 言语座位通用化 + echo 戒律（loop 内核 + prompt 面）

- `checkpoint_route` 删白名单：任何非终态工具 + 散文非空 + 参数校验通过 → execute 前发射 checkpoint（iteration 不限；`checkpoint_eligible` 注册表键退役）。终态工具散文留账本守卫不动。
- `MAX_CHECKPOINTS_PER_TURN` 2 → 4，注释重新定性为节奏护栏。
- prompt 面三改（改完必过 `scripts/prompt_gate.py`，ADR-071 T2）：
  - 相位叙事律：读前预期句 / 读后小结句合法且鼓励；逐调用旁白禁；
  - echo 可见性戒律：dock 后 echo 禁指无 confirmed run 时的「工作空间/画布」；禁复述计划组成；歧义消息起始句先承诺模式；
  - `_read_tools.j2` / intent 契约相关座位逐处核对（一部法只在一个座位说——checkpoint 座位通用化后，ADR-104 留在 prompt 里的资格措辞同步清扫）。
- `PresentPlanArgs.tasks[].params` 空串读容忍（`''` → `{}` 归一后校验）；同类终态工具（ask_user / propose_candidates 等）盘点同牙补齐。

### W5 — 迁移 + 回归座

- 一次性迁移脚本：存量 `activity_log` 行按帧时刻物化为单帧数组行并插 seq；物化不了的接受缺失（greenfield 口径）。脚本入 `apps/api/scripts/`，跑前先 dry-run 印目标（对齐 reset_db.py 纪律）。
- 纯测试：`tests/` 新增数组语义套件（append/update/settle reducer、折叠纯函数、checkpoint_route 通用化判定矩阵、params 容忍）；既有 `test_tool_loop_pure.py` 的 checkpoint 路由用例按新律改写。
- 剧本：`scripts/chat_scenarios.py` 增「多读回合 + 中途相位句」场景（断言：开工句行序 < 读行序 < 终答行序；刷新回放序恒等 live 序）。

## 4. Prohibited Behaviors

- 禁在渲染层再发明任何「重算顺序」的逻辑（时间戳混排 / 锚点推导 / 闩锁过滤）——数组序是唯一序。
- 禁给 activity 行做「每回合聚合行」的兼容形态——旧形态整删，不做双写过渡（greenfield 验收口径）。
- 禁把 checkpoint 资格以任何形式复活（白名单 / 工具元数据位 / prompt 措辞暗门）。
- 禁动 DeferredFrames 言语提交协议、打字机两牙、口头确认律、StatusLine 一座两行、画布可见性闸（ADR-105）——本批全部保留承重。
- 禁在 echo/相位句里新增任何指向「工作空间/画布」的措辞模板；冻参模板永禁（ADR-058）不变。
- checkpoint 发射座时点禁移到 execute 之后（ADR-104 撤回窗论证承重）。
- 禁扩 scope：画布计划预览（讨论中已否）、活动行跨项目聚合、right-rail 时间线——均不在本批。

## 5. Acceptance

1. **取证母本回放**：项目 3e333147 的「竖屏切片」回合重跑（同素材同提问）——开工句先于一切读行出现；刷新/切 tab 后消息流逐行恒等（含【已完成理解】类历史活动行）；连续检索行折叠为一行可展开。
2. **回放恒等性**：任意回合 live 结束后硬刷新，消息流顺序与内容逐行 diff 为零。
3. **失败回合诚实**：回合中止/失败后，已发生的 activity/checkpoint 行以 failed/cancelled 态留存，刷新后仍在。
4. **prompt 面**：`prompt_gate.py` 全探针 PASS；dock 后 echo 抽样无「工作空间/画布」指向、无计划组成旁白。
5. 既有纯测试基线零 regression；chat_scenarios 受影响座同步修订后全绿（用户自跑，CLAUDE.md Testing 纪律）。

## 6. Docs Update（随批收口）

- `docs/CHAT_ARCHITECTURE.md`：排序律改写为「数组位置律」（walk key 段删除）；checkpoint 座位段按 ADR-109 重写；活动行折叠规格入 §渲染节。
- `docs/PROGRESS.md` §0.2 状态回填 + commit 号。
- 需求池「一回合多交付（ADR-085）」行标记已吸收（落档时先行注记）。
- 本简报完成后归 `docs/archive/tasks-done/`。

## 7. 工期估算

W1+W2（服务端数组地基）≈ 3 天；W3（前端单路径 + 折叠）≈ 2.5 天；W4（内核 + prompt 面 + gate）≈ 1.5 天；W5（迁移 + 回归 + 验收缓冲）≈ 1.5 天。合计 **~8.5 工作日**（velocity 80% 口径）；依赖 = Agent Working Loop 迭代三 live 验收收口（共享 ChatDock 承重面，避免双线改同一文件）。
