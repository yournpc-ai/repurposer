# 展示文案二源律 + 卡面直改确定性通道修复批（ADR-058 施工记录）

> 状态：**已收口（2026-09-09）**。决策 = `docs/DECISIONS.md` ADR-058（现行事实源，本简报只是施工与取证记录）。
> 驱动：同日用户四截图走查——Post 卡面 prompt 直改 "Write post, in Chinese" 的连环五伤（§1）。
> 先读：ADR-058（翻案表：ADR-057 §6 通道律 / ADR-041 D8 focus）、`docs/CHAT_ARCHITECTURE.md` §5/§8.6/§8.7（现在时）、根 CLAUDE.md（打字机律 + 展示文案二源律段）。

## 1. 问题陈述（用户实测原话提炼）

英文 UI，结果画布，Post 卡已有 "Write post, in EN" 程序。用户改成 "Write post, in Chinese" 点发送：

1. **卡面回闪**：卡面恢复成旧程序，右侧 chat 自动发出该消息——直改骑 chat 通道，无乐观回显。
2. **死窗**：回声 "Drafting a Chinese LinkedIn post..." 之后无任何动态 thinking——用户问「怎么回事？」。
3. **任务列表突现 + 排序错乱**：过了一会 chat 突然变 tasks 态；终态时回声掉到 "Post (English) 24s" 收据下面。
4. **收据标题错**："Post (English)"——用户要的是中文。
5. **收官句错**："Your Post (English) is ready"。

## 2. 取证结论（根因链，全部实证）

1. **投影漂移（③⑤同根）**：收据标题与收官句读 dock 组件的 `intent` state（首个任务书 "Post (English)"），chat 派发回合早退（`if (data.run_id)` 分支不 setIntent）→ 世界真值（run 步骤 "Post · ZH"、提案 summary "Chinese"）在手里却被扔掉。
2. **时间锚假设倒挂（③排序）**：`runStreamUnits` 假设回声先于 run 出生（终态收据锚 `runStartAt + 1`）——book 路径成立，chat task_list 回合先建 run 后落回声消息（service.py 2590 区域），created_at 倒挂 → 收据跳到回声上方。
3. **回合状态机只覆盖前半（②死窗）**：thinking 行只活到首个 delta（`previewSeen` 门），结构化尾巴（提案 JSON → dispatch → run 出生）零状态主。
4. **LLM 自由在代码该决定处（①④的深层）**：chat_intent 对卡面直改选了 TaskListProposal 而非 WiringProposal edit_prompt——用户字面程序被丢，且确定性手势被绕成意图回合（三份多余言语：回声/收据/完成行）。
5. **写死的展示文案**："Post (English)" = 冻参模板拼接——参数在说话，于是有「文字核对」问题；thinking 行同病。

## 3. 拍板（用户原话锚）

- 「是在打补丁，我们似乎把一些可以让 llm 生成的文案，写得太死了」→ **展示文案二源律**（LLM 建图时命名 / 世界自证，冻参模板永禁）。
- 「节点级 run，dock 应该不产生任何消息——loading 加载也有，prompt 也变了，产物也变了，谁看不出来？」→ **卡面直改 = 确定性图动作零消息**。
- 「删除 working focus，只走 prompt mention」→ **focus 全层退役归 @mention**。

## 4. 施工清单（已落）

**后端（apps/api）**
- `models/schemas.py`：TaskListProposal / WiringProposal / InferredIntent 增 `name`（null 读容忍，打字机律牙①同纪律）；`ChatRequest.focus_output` 删除；`FocusRef` 收窄读侧（`ChatMessageResponse` 保留）；新增 `GraphReviseRequest/Response`。
- `pipeline/orchestrator.py`：`TaskSpec.name`（→ `run.context.name` via model_dump）。
- `chat/prompts.py`：chat_intent 形态 A/E + intent_router 增 `name` 规则（2-6 词、界面语言、命名作品）；焦点目标规则删除。
- `chat/service.py`：`_create_run_from_tasks(..., name, on_phase)`——dispatch 前 emit `creating_run` 相位帧；五处派发点传 name；`_propose_turn` 去 focus_output_id；`prepare_chat_turn` 停写 focus_output。
- `agents/contexts.py`：焦点注入块与 `focus_output_id` 参数删除。
- `pipeline/routes/projects.py`：新端点 `POST /projects/{id}/graph/revise`（202）——ops 代码构建（edit_prompt + run）→ `apply_wiring_ops` 唯一写门 → `tasks_for_graph_nodes` → `create_run` 唯一出生口；run 盖章 `context.origin="node_revise"`；credits/WiringRejected/ValueError → typed 422。
- `pipeline/routes/outputs.py`：regenerate 的 ChatRequest 构造从 focus_output 改骑 @output mention。

**前端（apps/web）**
- `chat/ChatDock.tsx`：`runTitle = runTitleOverride ?? planSummary`（planSummary = `intent.name || 链推导`）；信封 `if (data.run_id)` 分支从回声行 intent 盖章标题 + `finalizePreview` 盖 runId（排序锚）；零 delta start 走 `paceSettledProse`（打字机律最后闸门补齐）；thinking 行改整回合（`chatBusy` 全程），`previewSeen` 删除；focus props / sendRevision / focus 载荷全删（FocusRow 留作旧行回放）。
- `chat/…runStreamUnits`：终态收据锚 = `max(run 出生, 生产回声) + 1`。
- `lib/chat-stream.ts`：`ChatTurnBody.focus_output` 删除。
- `flow/types.ts` / `FlowView.tsx` / `FlowNodeCard.tsx`：`pendingProgram` 乐观回显（确认后卡面恒显用户字面程序，stamp 对齐即收，永不回闪）。
- `flow/ResultsCanvas.tsx`：`onNodeRevise` 替换 `onRevise`；`focusedOutputId` → `selectedOutputId`（纯选择）。
- `routes/projects.$id.index.tsx`：`handleGraphRevise`（POST graph/revise，credits 422 typed toast）；「在对话中指认」动作 = `insertMention`；`initialRunId` 对 `origin="node_revise"` 放行不聚焦。

## 5. 验收（用户自跑——本批未跑验证）

1. 卡面直改 "Write post, in Chinese" → 卡面立即显示新程序（无回闪）、dock 零消息、节点自跑、产物中文。
2. chat 发同样指令 → 回声打字机出现 → thinking 行全程（creating_run 相位）→ 收据标题为 LLM 命名（中文相关）、回声恒在收据上方、收官句同名。
3. 刷新 / 历史回放：旧 focus 行灰行前缀照渲染；新 run 标题从 run.context.name 重建。
4. 积分不足：graph/revise 的 422 走 typed toast（余额/所需）。
5. `npx tsc --noEmit`（施工时已过）；改 pipeline 代码后**重启常驻 worker**。

## 6. 挂账（不在本批，PROGRESS 需求池登记）

- **步骤级 LLM 命名**：per-task `name`（「tasks 的步骤也是 LLM 命名」的全量形态）——下一命名批；本批 `taskLabel` 链推导收窄为回退。
- **stub 塌缩**："No source material" 行塌缩。
- **mobile OutputChatCard 核对**。

## Prohibited Behaviors（本批新增，已入 CHAT_ARCH §12）

- 禁冻参模板当用户文案（参数永不拼接成标签说话）。
- 禁给确定性手势配 chat 回声（graph/revise 零消息通道）。
- 禁收据 / 收官句读 dock 组件 state（只读 run 真值 / 提案 name / 链推导回退）。
