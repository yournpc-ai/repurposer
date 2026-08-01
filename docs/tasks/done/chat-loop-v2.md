# chat-loop-v2 实施简报——chat 主交互面（UI + DAG 内核接线）

> Status: ✅ 已落地（2026-07-26：P1 ChatModal+RunCard / P2 translate_clip+dub_clip+MentionPicker / P3 edit ops 接线+OpsCard 全通并实测；regenerate_output 未注册——revise_script 已覆盖"再来一版"，防重叠）
> 依据：`docs/CHAT_ARCHITECTURE.md` §3（dispatch 三类目标）/§7（mentions）；`docs/tasks/done/chat-loop-v1.md`（v1 地基已在 main）；`docs/tasks/done/operation-model.md`（edit ops 地基，并行简报）
> 无新表 / 无新队列认领源 → 无需 ADR（v1 同判例）；新名词登记见 §7
> 用户裁决（2026-07-26）：①用户感知面 = **一个 chat 对话窗**（modal），窗内展示动作状态 + 产物结果；②产物结果**与 results 页的 outputs 卡片是同一组件**，不做缩略图特化；③chat 改完关掉窗，外面 results 该项即是最新（同一 output 行，无第二数据源）；④窗可关可开，对话继续（历史持久化已在）；⑤UI 用 shadcn chat 组件（已装）；⑥DAG 画布 UI 不做，只做内核（chat 操作 DAG = plan 级 dispatch + edit ops）

## 0. Context 与范围裁决

v1 已交付：intent 二态契约（task_list / edit_ops）、mentions 座位、compile_graph 模式②、skill registry 初集、SSE run events、节点量化摘要（spec.summary）。v1 是"UI 冻结版"——现存 `AssetChatModal` 是旧契约的临时态：纯文本轮次、pollRun 2s×60 轮询、无步骤状态、无产物内联。

v2 交付 **chat 主交互面**：modal 内完成"发指令 → 看动作逐步点亮 → 产物卡片就地出现 → 关窗外面已是最新 → 开窗继续聊"的完整闭环，同时接通 dispatch 三目标的另两类（edit ops / plan 级）。

**范围裁决**：
1. **asset-scoped modal 是本轮唯一入口**（results 页产物卡片唤起）；project 级 chat 座位（`asset_id` 可空）维持，不接 UI。
2. **产物内联 = 复用 results 卡片组件**（ClipCard/PostCard/…），加 `variant="chat"` 收敛操作区（保留 Open in editor，收掉与 modal 场景冲突的入口）；**禁止复制卡片 JSX 另造一套**。
3. **run 结果卡（RunCard）= DAG 的线性投影**：步骤清单（kind + 量化摘要 + 状态灯）+ 终态产物卡片，数据全部来自既有 SSE/outputs API——DAG 不可视化的决策不变（NAMING"用户不见图"），RunCard 不是画布。
4. **内核 = 两个家族的 dispatch 接通**：edit ops（产物级，依赖 operation-model 简报 Phase 1）+ plan 级（节点级，本轮 §4）；追加处理类（remove_filler/add_music 同族）v1 已通，本轮只做 skill 覆盖面扩充（§4.3）。
5. **undo 入口**：chat 内对 edit ops 消息提供"撤销本次修改"按钮（调 operations undo 端点）；历史面板/版本时间线不做（operation-model 简报已后置）。
6. **不做**：mentions picker 之外的 @ 语义解析花哨功能（"第二条"这类序数解析交给 intent agent 的 target_output_id，不做前端 NLP）、DAG 画布、project 级 chat UI、多 modal 并行。

## 1. 已核实的现状事实（读码确认）

- **shadcn chat 组件已装**：`ui/message-scroller.tsx` / `message.tsx` / `bubble.tsx` / `marker.tsx` / `attachment.tsx`（2026-06 批次，conversation 层：滚动锚定/消息行/气泡/状态行/附件；**无 composer 组件**——输入区自建，沿用 composer 惯例：Textarea + h-9 圆形发送钮）。
- **AssetChatModal 现状**：Dialog + 上述组件；turns 纯文本；`pollRun` 2s×60 轮询 `/projects/{pid}/runs/{run_id}`；关窗即弃轮询；`onUpdated` 回调触发 results refetch（同步外面=已实证的机制，保留）。
- **chat API**：`POST /chat` 同步返回 `{conversation_id, user_message, assistant_message, run_id}`（assistant 消息即时落库，content=proposal.summary，workflow_run_id=run_id）；`GET /chat/conversation?project_id&asset_id&asset_type`（404=无会话）；`GET /chat/conversations/{id}/messages`（含 workflow_run_id / intent / mentions）。
- **SSE**：`GET /projects/{pid}/runs/{run_id}/events`——先发 `run.snapshot`（run + 全部 steps 帧），再发 `step.updated`/`run.updated` diff，**终态自动关闭**。⇒ 历史回填与实时跟踪**同一条代码路径**（打开即得快照，终态即关），这是本轮最重要的一个已核实事实。
- **步骤帧**：`StepResponse{id, kind, status, seq, error, cost, stage, summary}`——summary = 量化摘要（35d622e 已在）；**`output_refs` 列在 WorkflowStep 上但没进 StepResponse**——需补（§3 改动点，一行）。
- **mentions 契约**：`ChatMention{type: asset|output|transcript_segment|workflow_step, id, label}`，列与 schema 已在；picker UI 是座位。
- **edit ops**：`EditOpsProposal` v1 回边界文案；operation-model 简报 Phase 1 落地后由本简报 §5 接线（registry 校验 + source=chat + message_id 血统）。
- **plan 级**：ROADMAP §3"节点重跑·追加·参数"❌；定向重生成小拓扑（revise_script target_output_id）是已实证的机制先例——plan 级 dispatch **复用模式②小图，不新建重跑 API**（§4 决策）。
- **outputs 同步**：chat 改动与 results 页读写同一 outputs 行；results 页自身有 SSE/轮询处理 latest run——关窗后外面自动最新，无需跨组件事件总线。

## 2. 设计论证（评审沉淀区）

### 2.1 RunCard 数据契约（assistant 消息 → 卡片的映射）

一条 assistant 消息 = 一次响应。三种形态：

| 形态 | 判定 | 渲染 |
|---|---|---|
| 纯文本（反问/边界/失败兜底） | `workflow_run_id` 空且无 ops | Bubble 文本 |
| **RunCard**（task_list 已派发） | `workflow_run_id` 非空 | 摘要文本 + 步骤清单（SSE 驱动）+ 终态产物卡片 + 聚合行 |
| **OpsCard**（edit ops 已应用，§5） | intent 含 edit_ops 且有 operation 记录 | 摘要文本 + 已应用 op 清单 + 产物卡片（最新 spec）+ 撤销按钮 |

RunCard 渲染规则：
- **步骤清单**：SSE `run.snapshot`/`step.updated` 驱动（**pollRun 轮询整体删除**）；每行 = 状态灯（Marker）+ kind 标签 + `summary` 量化文本；进行中的行 shimmer（shadcn chat 批次的 `shimmer` 工具类）。
- **产物卡片**：终态（`run.updated` status=completed）后，收集 steps 的 `output_refs` → `GET /outputs/{id}` → 用 results 同款卡片渲染（variant="chat"）。clips 渲染中就位：render_status=pending/rendering 的卡片显示渲染态（ClipCard 已有该态），video_url 就绪后卡片自更新（轮询 outputs 或复用卡片现有逻辑）。
- **聚合行**：`run.updated.summary`（终态聚合，后端已有 aggregate_run_summary）。
- **历史回填**：加载消息列表后，对带 run_id 的消息**开同一个 SSE 端点**——快照即全量、终态即关，与实时路径零分叉。
- **Open in editor**：clip 卡片上的链接（`/projects/$id/clips/$clipId`，路由已有）。

### 2.2 modal 生命周期与"关窗继续"

- 窗内活跃 run 的 EventSource 随 modal 关闭而断开——**run 在服务端继续跑**（worker 认领，与 UI 无关）；results 页自己的 latest-run 跟踪会让外面保持最新。
- 重新开窗 = §2.1 历史回填：进行中的 run 从 SSE 快照继续点亮，已完成的直接静态呈现。
- 多 run 并发：同一 conversation 串行派发（v1 现状：一条消息至多一个 run），不引入并发管理 UI。

### 2.3 同步外面 = 同一 output 行 + refetch，无第二数据源

chat 产生的一切改动落在同一 outputs 行（run 小图改 render_spec / operations 改 render_spec）；modal 的 `onUpdated` refetch results（v1 实证）。**禁止**为 chat 另建"聊天产物"缓存层或消息内嵌产物快照——消息里只存 id 引用，渲染时读 outputs API。

## 3. 后端改动点（小，全在一处）

1. `StepResponse` 补 `output_refs` 字段（列已在，`workflow_step_to_response` 一行 + schema 一行）。
2. `GET /projects/{pid}/runs/{run_id}` 响应补 steps 数组（若现状不含——pollRun 只读 status，以读码为准；补 `list[StepResponse]`）。
3. 无新表、无新端点（SSE / messages / outputs 全复用）。

## 4. 内核：plan 级 dispatch（chat 操作 DAG）

### 4.1 决策：复用模式②小图，不建独立重跑 API

"重跑节点 / 改节点参数"的用户意图（"这条换德语"、"配音重做"、"再生成一版"）统一表达为 **task list → compile_graph 模式②的定向小图**（`[director_plan → X_gen(target_id)]` 先例）。理由：小图机制已有完整账簿（workflow_steps 血统/成本/SSE）；独立"重跑端点"会造出第二个执行通道，违反 create_run 零旁路硬约束。DAG 内核对用户可见的形态 = RunCard（§2.1），不是节点操作面板。

### 4.2 寻址：mentions 精确 + intent 语义，两级

- **精确**：mentions picker（§6）钉死 `output` / `workflow_step` id，intent agent 直接消费（契约已在）。
- **语义**：无 mention 时 intent agent 从会话上下文（`asset_id` 锁定的产物 + `_build_context` 的历史）解析 target_output_id——v1 已如此（EditOpsProposal.target_output_id），不新增机制。

### 4.3 skill 覆盖面扩充（本轮 registry 新增，逐个过评审登记）

| skill | 参数 | 说明 |
|---|---|---|
| `revise_script` | target_output_id, instruction | 已有（v1） |
| `remove_filler` / `add_music` | … | 已有（v1 实证） |
| `translate_clip` | target_output_id, target_language | 字幕翻译定向小图（端点逻辑已有，skill 化） |
| `dub_clip` | target_output_id, target_language? | 配音定向小图（同上） |
| `regenerate_output` | target_output_id, instruction? | 同参/变参重生成（小图重跑） |
| `trim_clip`? | target_output_id, start, end | **评评审**：trim 是秒级确定性操作——走 edit ops（operations 表）还是 skill 小图？倾向 edit ops（便宜、可 undo），skill 不注册 |

每个 skill 的 `spec.summary` 量化文案一并补齐（对标"Removed 12 fillers · 3 repeated takes"口径；repeated-takes 检测不进本轮，摘要口径按实际能力写）。

## 5. 内核：edit ops 接线（operation-model Phase 3 本简报侧）

依赖 operation-model 简报 Phase 1（operations 表 + service + registry）。本侧改动：
1. `EditOpsProposal` → 不再回边界文案：ops 过 registry 校验（EditOp schema 收紧 extra=forbid，op 名必须命中 registry）→ `operations/service.apply_operations(source="chat", message_id=<assistant 消息>)` → assistant 消息渲染 OpsCard（§2.1）。
2. 校验失败（未知 op / params 不过）→ 走 v1 已有的 SkillRejected 修复轮同款路径（一次有界修复，败则 _cannot_do_text）。
3. "撤销本次修改"按钮 → `POST /outputs/{id}/operations/undo` → 卡片刷新（outputs refetch）。
4. `_EDIT_OPS_BOUNDARY_TEXT` 退役。

## 6. 前端结构与组件

```
components/chat/
  ChatModal.tsx        # Dialog 容器 + 会话加载 + 发送（替代 AssetChatModal，旧文件删除）
  RunCard.tsx          # 步骤清单 + SSE 订阅 + 产物卡片 + 聚合行（§2.1）
  OpsCard.tsx          # edit ops 应用结果 + 撤销（§5）
  MentionPicker.tsx    # @ 拣选器（output / workflow_step 两族，契约已在）
  composer 区          # Textarea + mention 按钮 + h-9 圆形发送钮（自建，沿用 composer 惯例）
```

- results 卡片复用：`ClipCard` 等加 `variant="chat"`（收敛操作区，保留 Open in editor）；**禁复制 JSX**。
- 打开入口：results 产物卡片的 Chat 操作（AssetActionBar 已有入口，换挂 ChatModal）。
- i18n：`chat.*` 命名空间（`assetChat.*` 旧键随旧组件删除而清理）；en.ts 先行，zh.ts 镜像（TS 强制）。
- 主题/圆角/阴影惯例遵守 CLAUDE.md（rounded-md、卡片无 ring、overlay-surface 浮层）。

## 7. 命名登记（随实施进 NAMING 词汇表）

| 中文 | 英文 | 定义 | 不是什么 |
|---|---|---|---|
| 结果卡 | `RunCard` | assistant 消息内嵌的 run 线性投影（步骤+产物+聚合） | 不是 DAG 画布 |
| 操作卡 | `OpsCard` | assistant 消息内嵌的 edit ops 应用结果 | — |

## 8. 分期与验收

| 期 | 内容 | 验收 |
|---|---|---|
| **P1 RunCard + modal 重构** | §3 后端两点 + ChatModal/RunCard + SSE 换轮询 + 产物卡片内联 + 历史回填 + i18n | 手测全链：发"去口头禅加音乐"→ 步骤逐条点亮（无轮询）→ 终态出现 ClipCard（渲染态→可播）→ 关窗 results 该项最新 → 开窗历史完整（含 RunCard 静态态）→ 刷新页面历史仍在 |
| **P2 skill 扩充 + mentions picker** | §4.3 三个新 skill + 摘要文案 + MentionPicker | curl："把这条翻成德语"→ translate_clip 小图 → RunCard 出现；@拣选器钉 output 后发指令命中 |
| **P3 edit ops 接线** | §5 全部（依赖 operation-model Phase 1 已合并） | curl："删掉第二句"→ spec 真变 + OpsCard + 撤销按钮回滚 + operation 行带 message_id |

依赖序：P1 无依赖可立即开工；P3 依赖 operation-model 简报 Phase 1（并行进行）。

## 9. 禁止行为（Prohibited Behaviors）

1. **禁轮询复活**：run 状态只走 SSE（`/runs/{id}/events`），pollRun 模式整体删除。
2. **禁复制产物卡片 JSX**：内联 = results 卡片组件 + variant；发现第二套卡片 markup 即违规。
3. **禁消息内嵌产物快照 / 另建 chat 产物缓存**：消息只存 id 引用，产物唯一来源 = outputs API（ADR-030）。
4. **禁绕过 `orchestrator.create_run`**：plan 级动作一律 task list → compile_graph 模式②小图，不建独立重跑端点（v1 硬约束延续）。
5. **禁 ReAct / 轮内多轮 tool calling**（v1 硬约束延续）；edit ops 必须过 registry（operation-model 简报约束延伸）。
6. **禁 DAG 可视化元素进 modal**（节点图/连线/画布——"用户不见图"决策不变；检视面是 P2 独立议题）。
7. **禁新表**：本轮零迁移（output_refs 进 StepResponse 是响应形状变更，不是迁移）。
8. **禁 composer 区引入粗圆角/加粗药丸**等违反 CLAUDE.md UI 约定的样式。
