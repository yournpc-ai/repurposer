# 选项唯一座位 — 施工简报（ADR-100）

> Status: **O1/O2 已落地**（验证全部未跑，用户清单见末节——验证绿后做 O3 文档收窄）。架构母法 = ADR-100（翻 ADR-099 §2 suggestions 行 / §3 / §4 answer 面，恢复 ADR-081 全强度）。**验证纪律：一切 pytest / prompt_gate / 剧本 / live 复跑由用户自跑**；施工会话只做代码层分析与 review，未跑项在批次 Status 在册。

## 冻结事项（本简报全程不再议）

消息流零选项（无例外形态、无「换视觉区分」方案）；answer 纯信息、浏览问 = ask_user；trigger 建议 dock 全机器原样保留（wrap_up 校验 / 行 stamp / answer endpoint ref 重构 / 落地解算与 stale note）；存量列保留不清洗不迁移；谱系其他三档、交互宪法、言语提交协议不动；不重开 suggestions→mentions（ADR-099 已否）。

## 拆除面盘点（施工前 grep 复核，以代码为准）

| 面 | 拆除 | 保留（trigger 机器，零改动） |
|---|---|---|
| schema | `PlanAnswerArgs.suggestions` / `ChatAnswerArgs.suggestions` 两字段（schemas.py） | `SuggestionItem` / `dock_worthy_suggestions`（wrap_up 消费）/ `SuggestionRecord` / `SuggestionRef` / `ChatRequest.suggestion_ref` / `AnswerRequest` 不动 |
| turn | `plan_turn.py` / `propose_turn.py` 的 answer 路径 `stamp_suggestions` 调用与 `params.suggestions` 读取 | 两 turn 的 `resolve_suggestion_note` 消费（trigger 点选经 `_continue_chat_answer` 重构 ref 骑入，同一条链） |
| service | answer+suggestions 专属消费（如有，以 grep 为准） | `stamp_suggestions`（trigger_turn:558 在调）/ `_suggestion_ref_for` / `_continue_chat_answer` ref 骑传 / `resolve_suggestion_note` 本座 |
| prompt | `intent_router_system.j2` suggestions 契约段 / `chat_intent_system.j2` 同款段 / `turn_tools.py` answer catalog 描述 ×2（建议条款句） | trigger_system.j2 的 SUGGESTIONS 段（dock 机器的法） |
| 前端 | `ChatDock.tsx` suggestionOptions 渲染块 + `handleSuggestionOptionPick` + suggestion_ref 发送；`historyReplay.ts` `suggestionOptionsOf` 及其消费；`chat-stream.ts` `suggestion_ref` wire 类型（发送面） | `questionDock.recommended` i18n（dock 选项共用键）；trigger dock 一切 |
| harness | `chat_scenarios.py`：`elicit_suggestions_turn` / `check_suggestion_block` / provenance 重放段（~5019-5160 一带）与一切 answer+suggestions 断言 | trigger 建议 dock 断言（~1544-1574 / 4756 一带——它们锁的是保留面） |
| gate | `prompt_gate.py` probe I 改靶（见 O2） | 其余 11 探针 |

**易踩边界**：`resolve_suggestion_note` / `compose_suggestion_note` / `suggestion_stale_reasons` / `build_suggestion_records` 四函数**全保留**——trigger 点选链（`_continue_chat_answer` → ChatRequest.suggestion_ref → plan/propose turn 解算）在消费。本批死的唯一解算 wire = 前端 inline 卡的 suggestion_ref 发送。

## 批次总序

```
O1（行为翻转）→ O2（死码清扫 + harness 改靶）→ O3（文档现行法收尾）
```

- O1 落地后模型结构性不可发射 suggestions（schema 字段与 catalog 同步删除 = catalog 即开关），前端不再渲染——行为翻转集中在一个 commit，可整体 revert。
- O2 是零行为变化的死码清扫 + 测试面改靶，与 O1 分开 commit 保归因隔离（行为回归归 O1，测试面问题归 O2）。
- O3 只在 O1/O2 验收绿后做，docs 一次性写现行法。

---

## 批次 O1：行为翻转（单 commit）

| 字段 | 内容 |
|---|---|
| **scope** | 模型面与渲染面同步拆除：answer 两份契约的 suggestions 参数 + prompt 两处契约段 + 前端 inline 建议卡全链。仅此。 |
| **files** | `apps/api/app/models/schemas.py`（`PlanAnswerArgs` / `ChatAnswerArgs` 删 suggestions 字段）；`apps/api/app/chat/turn_tools.py`（answer catalog 描述 ×2 删建议条款句 + ask_user 描述 ×2 补浏览问的家）；`apps/api/app/prompts/chat/intent_router_system.j2` + `chat_intent_system.j2`（删 suggestions 契约段 + ask_user 路由补浏览问的家）；`apps/api/app/chat/plan_turn.py` / `propose_turn.py`（answer 路径 `stamp_suggestions` 调用删除——**编译耦合强制同 commit**：schema 字段一删，`params.suggestions` 读取即 AttributeError，不是简报原假设的恒空 no-op）；`apps/api/app/chat/suggestions.py`（provenance note 措辞 card→dock，prompt 卫生律——模型面文本永不命名已退役形态）；`apps/web/src/components/chat/ChatDock.tsx`（suggestionOptions 渲染块 + handleSuggestionOptionPick + suggestion_ref 发送）；`apps/web/src/components/chat/historyReplay.ts`（`suggestionOptionsOf` 及其消费点 + 测试文件同步）；`apps/web/src/lib/chat-stream.ts`（发送面类型）；`apps/api/tests/test_answer_suggestions_pure.py` → `test_suggestion_provenance_pure.py`（收窄 + 改名——answer args 零 diff 锁换形态翻案锁，trigger 机器锁全保留） |
| **depends_on** | 无（独立批） |
| **must_not_touch** | trigger 一切（trigger_turn / trigger_system.j2 / wrap_up schema）；`resolve_suggestion_note` 及其两 turn 消费；`questionDock.recommended`；answer 的其他契约语义（bare answer 拒绝等）；stream semantics / DeferredFrames |
| **acceptance** | ① 浏览问 / 下一步方向场景 → ask_user dock 选项问（阻塞形态、推荐标记、default_path、×/铅笔退出面）；② answer 任何场景零建议卡；③ 历史 answer 行的建议块不渲染、散文保留（读容忍零 crash——`suggestionOptionsOf` 删除后历史行天然无渲染座）；④ 行为翻转零半成品：schema 无字段 + catalog 无描述 + 前端无渲染，三面同 commit |
| **rollback** | 单 commit git revert |

## 批次 O2：死码清扫 + harness 改靶（单 commit）

| 字段 | 内容 |
|---|---|
| **scope** | O1 留下的死调用清扫 + 测试面从 answer+suggestions 改靶 ask_user。零运行时行为变化。 |
| **files** | `chat_scenarios.py`（`elicit_suggestions_turn` → `elicit_options_dock_turn` + 新 `check_options_dock` 谱系锁；S-int-2/5 改靶 ask_user 选项 dock；**S-int-6/7 删除**——answer 面点选/stale 回路随形态消亡，改靶无对象；`resolve_note_in_process` / `latest_user_row` / `SuggestionRef` import 随删；`check_suggestion_block` 保留给 S-int-11 trigger 座）；`prompt_gate.py`（probe I 改靶 browse→ask_user：终态 ask_user + 1-3 options + present_plan 零调用；failure tag 改 `terminal=*` / `options-range`，`ask_user-called` tag 随改靶消亡；阈值 8 不动——改靶后首读建带，recalibrate from readings, never to excuse） |
| **depends_on** | O1 验收绿 |
| **must_not_touch** | trigger 建议 dock 断言（保留面的锁，一字不动）；probe I 之外探针；阈值不动（改靶不降为红而调阈） |
| **acceptance** | ① `prompt_gate.py` 全绿（改靶后 probe I 在册）；② 全量 `chat_scenarios.py` 绿，红全部归因（既有债清单核对先行）；③ 纯 pytest 绿（既有债除外）；④ grep 零残留：`suggestions` 在 answer 面（两 args / 两 j2 / 前端）无引用 |
| **rollback** | 单 commit git revert；probe I 改靶红 = 登记读数、不回调阈值 |

**O1 落地记录**（施工会话交付，验证全部未跑）：

- **划分修正**：简报原假设「stamp 调用 O1 后恒空 no-op 归 O2 清扫」不成立——schema 字段一删 `params.suggestions` 即 AttributeError，两 turn 的 answer 路径 stamp 调用与 import 强制并入 O1。O2 随之收窄为纯 harness 面。
- **浏览问接档**：suggestions 契约段不是纯删除——两 j2 的 ask_user 路由行与 turn_tools 的 ask_user catalog ×2 同步补「open exploration / browsing questions 的家」（方向 dock 成选项、一词可答、default path 保持可跳过），否则浏览问无档可去 = 事故④温床复开。
- **note 措辞**：`compose_suggestion_note` 的 "suggestion card" → "options dock"（prompt 卫生律——模型面文本永不命名已退役形态；机器与三谓词零改动）。
- **测试面**：`test_answer_suggestions_pure.py` → `test_suggestion_provenance_pure.py`——answer args 零 diff 锁换成形态翻案锁（dump 无 suggestions 键 + extra="forbid" 拒收 stray payload），WrapUpArgs/records/stale/note 锁全保留。
- **grep 零残留已核**：前端 `suggestionOptions`/`suggestion_ref` 发送面零引用；后端 answer 面 `params.suggestions` 零读取（trigger 的 `WrapUpArgs.suggestions` 与 stamp/resolve 机器全保留）。
- **未跑验证（用户清单）**：见末节全量。

**O2 落地记录**（施工会话交付，验证全部未跑）：

- **S-int-6/7 删除而非改靶**：点选/stale 回路是 answer+suggestions 形态专属（客户端 suggestion_ref 发送面已死），改靶无对象。trigger dock 点选链（`_continue_chat_answer` ref 重构 → resolve）机器原样在跑，但**剧本覆盖随之归零**——现只剩纯测试锁三谓词与 note 文本，trigger 点选 → 编译 / stale 具名 的端到端场景是新覆盖缺口（承重观察①）。
- **S-int-5 setup 卫生**：改靶后 setup 会 dock 真实待决问题，先 bail 再发浏览问（防 pending_disposition 判定吃掉浏览回合）。
- **probe I**：谓词 = `ask_user ∧ 1≤|options|≤3 ∧ present_plan 零调用`；failure tag `ask_user-called` 消亡（ask_user 从负形变目标），新增 `options-range`。
- **承重观察（在册不处理）**：① trigger 点选链剧本覆盖缺口（上条）；② S-int-2/5 的 dock 发射率是新方差面——`elicit_options_dock_turn` 的纯散文 answer 重试口径与旧卡发射同形，首跑读数若系统性偏低 = prompt 接档措辞待调，不是场景松劲；③ `check_options_dock` 不锁选项 id 语法（plan 路 model 自填 id，只锁非空唯一指向）——若后续要统一 a/b/c 与 1/2/3 语法另批。
- **未跑验证（用户清单）**：见末节全量。

---

## 批次 O3：文档现行法收尾（O2 验收绿后同批）

1. **ADR-099** 收窄：§2 谱系表删 `answer`+suggestions 行（四档→三档）；§3 全节删除；§4 收窄为 trigger 建议 dock 的 provenance 座位（answer 面表述删除）；Consequences 中「浏览问有档可去（answer+suggestions）」改写为现行法；**翻案注随删**（内容已收窄，注记使命完成）。
2. **NAMING.md**：§151 终态交互形态行改写三档；§154 `suggestion_ref` / §155 `source_state` 两行收窄为 trigger 建议 dock 机器（删 answer 路径表述——「POST /chat 路径」句改写为 trigger 重构链单座）。
3. **README.md**：单一事实源表行（:48）更新——删 answer+suggestions / suggestion_ref / source_state 的 answer 面表述。
4. **CHAT_ARCHITECTURE.md**：grep answer+suggestions / 建议卡相关表述收窄（trigger 建议 dock 段不动）；answer 契约行同步。
5. 本简报 Status 收尾；验收全绿后移 `docs/archive/tasks-done/`（用户执行或授权执行）。
6. **PROGRESS.md**：需求池本批行状态更新；「建议卡发射率」行标记已随批消亡（substrate 方法已迁移 probe I 新靶）。
7. **commit**：`docs: ADR-100 收口——ADR-099 收窄 + NAMING/README 现行法 + 简报归档`

## 本批验收（用户自跑清单）

1. `cd apps/api && uv run --extra dev python -m pytest tests/ -q`（既有债清单核对先行——interaction-architecture 简报在册 11 红族，清单外新红 = 异常）
2. `cd apps/api && uv run python scripts/prompt_gate.py`（O2 后 probe I 新靶在册）
3. `cd apps/api && uv run python scripts/chat_scenarios.py` 全量
4. web tsc + 构建
5. live 复跑三场景：① 浏览问（「你能拿这素材做什么」族）→ dock 选项问变形、可点选可 ×；② 素材理解完成 trigger → 建议 dock 原样（回归面）；③ 能力问 / 闲聊 → 纯散文 answer、零卡片
