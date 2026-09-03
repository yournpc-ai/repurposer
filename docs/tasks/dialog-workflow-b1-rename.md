# B1 改名批施工简报——对话工作流批（ADR-052 判词 3，NAMING N-43~N-47）

> Status: ✅ 已落地（2026-09-03 当日完工——C1 pipeline 家族 + C2 chat 边缘 + C3 brief 家族 + 批尾文档层全落；验证由用户自跑：chat_scenarios 全量 / 真实 create_run 全链 / prompt-surface 零假设闸）。母文档 `docs/DIALOG_WORKFLOW.md` §3；判例 N-44（router/understand/plan）、N-45（pending_brief）。
> 唯一目的 = **换名，零行为变化**。prompt 文案 / schema 形状 / SSE / wire 语义 / 报价 / 拓扑全部不动。

## 1. 改名表（全栈同名，含注释与文档散文）

| 旧 | 新 | 层 |
|---|---|---|
| `director_understand`（kind 字符串） | `understand` | pipeline |
| `director_plan`（kind 字符串） | `plan` | pipeline（plan 一词归一主） |
| `DirectorUnderstand` / `DirectorPlan`（节点类） | `Understand` / `Plan` | pipeline |
| registry agent 实例 `director_understand` / `director_plan` | `understand` / `plan` | agents |
| spec 键 `plan_summary`（含 `_plan_summary` 函数） | `book_summary`（`_book_summary`） | pipeline（chat 侧只叫 book/brief） |
| `plan_agent`（StreamingAgent 实例） | `intent_router` | chat 边缘 |
| 散文词 PlanAgent / ChatIntentAgent | intent router | 注释 / 文档 |
| plan path（分派分支名 + `_plan_turn` + `plan_path` 分派位） | book path（`_book_turn` + `book_path`） | chat service |
| `presented_plan` | `presented_book` | chat service/intent |
| `pending_intent`（DB 列 + schema 类 + wire 字段） | `pending_brief`（`PendingBrief`） | 全栈 |
| 前端 i18n 键（en.ts/zh.ts 内 director_* / plan 族） | 同上新键（**值不动**） | web |

**不在本批**：`chat_intent_agent` 实例名——其归宿 = B2 相位合并的物理形态裁决（悬案④，间隔 1 天）。B1 给它改名只会产出活不过 48 小时的过渡名（`intent_router_pre/post` 违禁后缀律）。B1 落 `intent_router`（原 plan_agent）后，chat_intent_agent 暂存，B2 合并时归一。

## 2. Commit 切分（各自冷启动自绿）

- **C1 pipeline 家族**：kind 字符串 ×2 + 节点类 ×2 + registry 实例 ×2 + spec 键 plan_summary → book_summary + **数据迁移**（新 alembic：rewrite `workflow_steps.kind` 两值，b8e4f2a91c63 先例；String 列零 schema）+ i18n 键 + 前端 runFlow/FlowNodeCard 引用 + 文档散文。
- **C2 chat 边缘**：plan_agent → intent_router + plan path → book path（`_plan_turn` → `_book_turn`）+ presented_plan → presented_book + 注释/文档散文。
- **C3 brief 家族**：`projects.pending_intent` 列 rename 迁移（rename_column，**存量行随列走零丢失**）+ tables/schemas（`PendingIntent` → `PendingBrief`）+ routes/projects + chat/service + 前端（ChatDock / projects.$id——wire 字段同 commit 双端换）+ chat_scenarios。
- **批尾**：NAMING 词汇表行收尾（导演行删除、understand/plan/intent router/pending_brief 行去「未实施」注记）+ CHAT_ARCH / AGENT_ARCH / CLAUDE.md 散文换名 + chat_scenarios 全量复绿 + 一次真实 create_run 全链（steps 表出现 understand/plan）。

## 3. 验收

1. 全库 grep 旧标识符零命中（豁免：历史迁移文件、`docs/tasks/done/`、git 历史）。
2. 每 commit：`uv run python -m compileall app` 绿 + `uv run python -c "import app.main"` 绿 + web `tsc` 绿。
3. 批尾：chat_scenarios 全量绿（零假设 = 更名不影响任何剧本形态）；alembic `current == head`；手工 create_run 全链验证（剧本测试 验证姿势 memory）。
4. 零行为变化举证：同一项目 dock 的任务书 / SSE 帧序列 / run 拓扑在 C1~C3 前后逐字节一致（除更名字段名本身）。

## 4. Prohibited Behaviors

- **禁改写历史迁移**（b8e4f2a91c63 / a1c5e8f42d07 / d7e3b1a95c42 等 = 已应用历史，只读）。
- **禁兼容 shim / 双读容忍**（N-42 零容忍）：spec JSONB 旧 `plan_summary` 键不做 fallback——dev 存量 run 可清（FK 顺序清理 memory）；列 rename 之外不留第二通道。
- **禁行为变化**：prompt 一个字不改、schema 字段一个不动（除改名本身）、i18n 值不动只动键。
- **禁过渡名**：不发明 `intent_router_pre/post` 或任何带后缀的临时标识。
- **禁顺手改逻辑**：`apps/api/tests/` 残留两件（test_intent_layer_pure / test_stream_extract——测试套件已退役的遗留）只做机械换名，不修断言、不承诺转绿。
- **禁碰 B2 内容**：ask 动作 / brief 账本槽位 / 出书门槛一律不在本批。
