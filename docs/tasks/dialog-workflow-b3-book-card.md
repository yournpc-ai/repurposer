# B3 P1 施工简报——任务书卡 = brief 的渲染（ADR-052 判词 5/6，DIALOG_WORKFLOW §5）

> Status: 待开工（简报 2026-09-03 落，排期 PROGRESS W7：09-08）。前置 = B1 ✅ / B2 ✅（brief 账本 + ask + 出书门槛已入库）。
> 本批是**形态批**：卡面解剖定向改变（空文本框全删是交付物，不是回归）；wire 载荷只加不破（AskPayload 加 `brief` 字段，旧行无该键前端容忍渲染为零槽位——前端读取宽容，非服务端读容忍 shim）。

## 1. 变更表（蓝图片段 → 实现物）

| 蓝图（DIALOG_WORKFLOW §5） | 实现物 | 层 |
|---|---|---|
| 卡顶 = brief 槽位渲染（About / For / Tone / Material——有值显示，inferred 值可点改，无值不显示；零空框） | `AskPayload.brief: BriefLedger | None`（task_book  dock 时钢印合并账本进 question 载荷，随 turn 响应与初始 pending_brief 双通道抵前端）；卡组件渲染槽位行：user-stated 纯文本，inferred 虚线下划可点 | schemas + service + web |
| inferred 值可点改 | 点击 → 行内编辑（预填现值）→ 确认 = 经普通发送通道发一条用户消息（`受众：X` / `Audience: X`——router 按字面语句合并为 user-stated；**chat 仍是唯一修订通道**，点值改只是它的速写） | web |
| 两个空文本框全删（per-row focus + run 级 instruction） | 删 `meta.focus` Input 块与 TOOL_META focus 标记；删 instruction Textarea + `userInstruction` state + `withUserInstruction` 及其三个 ship 点（Start / refine prior_intent / 兜底）；`specific_instruction` 继续由 LLM 蒸馏隐形 ride（数据层不动）；`params.focus` 仍是合法参数（chat 可设） | web |
| 确认 pill 按动作命名 | i18n `confirmQuestion`：en `Save & generate?` / zh `保存并开始？`（Start 按钮文案不动） | i18n |
| 散文第二句恒为默认路径声明（schema 牙齿） | 卡面固定解剖位：echo 之下、任务链之上一条 muted 固定行（本地化静态文案）——「直接开始 = 我按这本书生成；想改什么，在聊天里说一句」。结构保证恒在，不依赖 LLM 记性；LLM echo 的 ≤2 句规则不动 | web + i18n |

**不在本批**：画布节点面（B 系已完成）；estimate/cost quote（W7 消耗批）；`chat_intent` 四态机的其他改动。

## 2. Commit 切分

- **B3-C1 一批一 commit（自绿）**：wire（AskPayload.brief + sync_task_book_question 钢印 + 调用点透传）+ 卡面换血（槽位行 / 删两框 / pill 改名 / 固定默认路径行）+ i18n 双语 + 死键清理 + harness 断言（S51 终态：dock 的 question 载荷 brief.topic = user-stated）。单 commit 理由：wire 与渲染互为依赖，拆开两端各自不可验。

## 3. 验收

1. **卡面零空文本框**（硬条）：任务书卡不再出现任何 `<Input>` / `<Textarea>`。
2. 槽位行：有值显示 / 无值不显示 / inferred 可点改 / user-stated 纯文本；material = none 不显示，attached/pasted 显示。
3. **不填任何东西直接 Start 的路径在卡上可读**（固定默认路径行）。
4. 点值改 → 发送 → 重 dock 后该槽位显示新值（来源变 user-stated）。
5. S1/S2/S3/S11/S16/S23/S27 dock 生命周期无回归（剧本 harness 全绿，用户自跑）。

## 4. Prohibited Behaviors

- **禁第二修订通道**：点值改必须经 chat 发送通道落成真实用户消息；禁私自开 slot-update 端点（禁第二意图入口不变量同义）。
- **禁空槽位渲染**：无值槽位（含 material=none）不显示，禁渲染占位符或 "not set"。
- **禁 LLM 簿记上卡**：reasons 键 / 来源键永不直渲成用户文案（既有纪律）；来源只作交互形态（inferred 可点），不作文本标签。
- **禁顺手改任务行**：任务行（数量/语言/删行/加任务）解剖不动；衍生预览行不动。
- **禁删数据层字段**：`specific_instruction` / `params.focus` 服务端保留（LLM 蒸馏与 chat 参数继续合法）；本批只删 UI 输入面。
