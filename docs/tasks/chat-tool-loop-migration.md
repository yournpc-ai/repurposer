# 会话层工具 loop 批 + decompiler 批 —— 施工简报

> Status: **T1~T4 已落地（2026-09-15）**——线格式三层 / 工具 loop 内核 / 触发回合 / 验收改写+NAMING 批 v3+文档现在时；T5（decompiler，ADR-078）待实施。需求模拟四轮讨论收敛，用户旅程母文档 = `docs/JOURNEYS.md`。
> 本文是实施的唯一工作简报；决策正文在 `docs/DECISIONS.md` ADR-077/078。完成后归 `docs/tasks/done/`。

## 0. 一句话目标

会话层从「单调用判决 + 方言机器」迁移为**标准有界工具 loop agent**（读工具一族 + 门动作工具 + 终态工具停环），生产层编译期封闭 DAG 零改动；随后以 decompiler（video → clip-spec 骨架）撑住终极旅程「把原视频做成案例那样子」。

## 1. 先读清单（按序）

1. `docs/DECISIONS.md` **ADR-077**（会话层工具 loop 化全部判词）+ **ADR-078**（decompiler）+ ADR-039（四层工程地图）/ ADR-052（厚 agent 判词——本条翻其否决收窄）/ ADR-064（顺形律）/ ADR-066（方言归 client）/ ADR-071（prompt gate）/ ADR-057（图即产品对象）/ ADR-053（提问机器）/ ADR-028（拓扑铁律）
2. `docs/JOURNEYS.md`——三条旅程逐拍与分支树（验收的参照系）
3. `docs/AGENT_ARCHITECTURE.md`（四层地图 + BoundedLoopNode 三护栏先例）+ `docs/CHAT_ARCHITECTURE.md`（提问机器 / SSE / 打字机律现行规格）+ `docs/DIALOG_WORKFLOW.md`（brief 账本 / ask 一等动作现行概念）
4. 代码：`app/agents/base.py`（Agent 漏斗 + StreamingAgent）/ `app/agents/contexts.py`（装配层）/ `app/chat/intent.py`（两个判决声明）/ `app/chat/service.py`（dispatch + 提问机器 + 结算）/ `app/chat/stream_extract.py`（ProseDeltaExtractor）/ `app/providers/llm/minimax.py`（Model 缝 + PRICING + _ThinkStripper）/ `app/pipeline/graph.py`（NodeBase + BoundedLoopNode）/ `app/tools/research/`（action-JSON loop 先例）
5. 前端：`apps/web/src/lib/chat-stream.ts` / `apps/web/src/components/chat/`（ChatDock / StatusLine / RunTaskList）

**避让**：画布三族批（ADR-072/076）并行施工中——`app/pipeline/graph_store.py` / `graph_fill.py` / `app/models/tables.py` / `apps/web/src/components/flow/` 本批只读不写（T2 的 `edit_graph` 工具实现调 `apply_wiring_ops` 公开签名，不动其内部）。

## 2. 批次切分（各自 commit 级自绿；顺序强依赖 T1→T2→T3；T4 随 T2/T3 滚动；T5 独立可并行）

### T1 线格式三层 + 错误去品牌化（Model 层）

- `providers/llm/`：client 能力旗标声明（`supports_native_tools` / `supports_json_schema` / reasoning 方言）；`MiniMaxClient` 加 tool_calls 通道（`generate_with_tools` / 流式同款：content 通道散文 + tool_calls 参数独立累积，spike 已验形态）；截断签名（finish_reason=tool_calls 但 arguments EOF）按 schema 拒收治走错误反馈。
- 三层法则：**层只换线格式，永不动判决契约**——Tier 0 地板（action-JSON loop，research 先例）/ Tier 1 原生 tool_calls / Tier 2 provider 特有；harness 选双方共持最高层，降级自动。
- 错误类型去品牌化：`MiniMaxError` / `MiniMaxSchemaError` → 中性名（如 `LLMError` / `LLMSchemaError`，user_key 税制不动）；PRICING 按 provider+model 分家。
- 验收：现有全部 agent 调用在新线格式下零行为变化（双通道 A/B 复跑剧本）；`tests/` 纯函数套件绿；prompt gate 过。

### T2 工具 loop 内核（Loop 层主体）

- **判决 union → 工具集**（机械翻译）：`ask_user` / `present_plan` / `start_run` / `propose_tasks` / `apply_edit_ops` / `edit_graph`；`type` 字段 = 工具名，各态字段 = 工具参数。
- **护栏搬进工具执行内**：出书门槛 = `present_plan` 执行内校验（无根 → 拒绝 + 结构化反馈）；出生地 422 不变（`start_run` → `create_run`）；`edit_graph` → `apply_wiring_ops` 唯一写口不变；dock 生命周期 / 单待决 / autoResume 结算 = 代码原样（工具调用驱动，非判决驱动）。
- **loop 驱动**（harness 新形态，`agents/base.py` 家族）：`max_iterations` 封顶（初值 ≤6）+ 终态工具（ask_user / present_plan / start_run / 最终回复）一调即停 + 报价 = fold。
- **读工具一族**（`app/chat/perception/` 新包 + 注册表）：首批 = `get_output_spec` / `get_understanding` / `list_caption_styles` / `search_music` / `get_run_status` / `get_asset`；纪律 = 只读（实现里没有写函数）、name + params schema + execute + 碎碎念文案键；固定 digest 装配（`contexts.py` graph block 等）同步瘦身——能被工具读到的不再预注（understanding 摘要不再固定注入 = B1 被本批吸收退役）。
- **SSE**：工具调用 = 相位帧新族（`inspecting`——「正在查曲库…」文案键随注册项）；散文 = content 通道；打字机律三牙重述到工具线格式（零 delta 路径 paceSettledProse 不变）。
- `service.py` 拆解：结算 / 生命周期代码搬进工具实现与 UI 状态机；dispatch 主从判词翻为 loop 驱动。
- 验收：JOURNEYS 旅程三全表逐条过（读 spec 改相对量 / 查样式库给选项 / 读曲库推荐 / 派生法语版）；剧本测试断言改为工具序列（S1–S12 全绿重写）；`prepare_chat_turn` 的 4xx 语义不变；失败回合零落库契约不变。

### T3 触发回合（主动发声 + 收官 reviewer + 建议 pills）

- chat 回合的「用户消息」可以是系统事件：触发器白名单首批 = **理解完成**（warm understanding 落地钩子）+ **run 完成**（终态帧后）；worker 侧写座（`dock_interrupt_question` 先例同族——pipeline 调 chat 服务函数）。
- 触发回合 = 标准工具 loop 回合：agent 借读工具看产物 → 收官散文（判断 + 取舍理由，**不复读清单**——ADR-077 判词③维持 09-04 recap 退役判词）+ 建议 pills（suggestions 载荷：点击 = 作为用户消息发出 / 或直达下载动作）。
- 前端：唤回复用（agent 发声即 dock 召回）；建议 pills 渲染与点击通道。
- 验收：JOURNEYS 旅程一 ②⑦ 与旅程二 ④；刷新/跨设备恢复（消息行持久化）；09-04「收官无下一步」翻案的断言 = 建议 pills 有据可依（引用真实产物事实）。

### T4 验收与文档（随 T2/T3 滚动收口）

- 剧本测试全量改写（断言 = 工具序列 + 终帧消息）；prompt gate 三探针适配新线格式并按 provider 参数化。
- **NAMING 批 v3**：方言词退役全表（提问机器 → ask_user、verdict → tool call、任务书 → plan、brief 账本 → session state…），每 commit 冷启动自绿；AGENT_ARCH §2.5 方言侧消融。
- `CHAT_ARCHITECTURE.md` / `DIALOG_WORKFLOW.md` / 本文相关节全量改写为现在时；CLAUDE.md 行为契约段同步。

### T5 decompiler 批（ADR-078，终极旅程内核——独立可并行）

- **decompiler 节点**（pipeline 内部 crew，编译期注入，永不进用户提议空间）：video → clip-spec 骨架。字段确定性分层：镜头切分/节奏/画幅 = 确定性检测（零 LLM）；字幕 preset/颜色 = 视觉最近邻枚举 best-fit；mood/hook 装置 = LLM 判断；内容槽位留空。产出 = 新内部产物类型（visible_outputs 过滤族），资产级 + 内容寻址 + 可复用。
- **资产角色**：source / reference（消歧问 or mention 指认；reference 常驻可回读；角色可反转）。
- **exemplar 参数源**：plan 装配签名加骨架输入；任务书参数第四来源（代码映射，LLM 永不写 spec）。
- 验收：JOURNEYS 旅程二分支树逐条过（角色消歧 / 无语音案例 / 素材撑不起结构 / 能力差距纠偏 / 角色反转）；骨架确定性字段零 LLM 介入断言；案例仿制 e2e（两视频进 → 产物出 → 后续修订）。

### B4 画布镜头跟随（纯前端，随时插入，不占批跑道）

- FlowView auto-follow：running 节点平滑居中，节点切换镜头游走；用户手势让位；run 终态拉远 fit。说明书画布（锁 fit）不动。

## 3. Prohibited Behaviors（本批禁令，全员适用）

- **禁止**执行 loop——loop 内零副作用；写世界只走三扇唯一门（edit ops / wiring ops / `create_run`），工具只是门铃。
- **禁止** LLM 塑形拓扑（ADR-028 不动）；exemplar 参数由代码映射，LLM 永不写 spec。
- **禁止**绕开 `apply_wiring_ops` / `create_run` 的第二写口；禁止读工具携带任何写。
- **禁止**引入 agent 框架（Agno / LangGraph / Mastra 依赖）——跟上标准 = 概念与词汇对齐，不是引入依赖。
- **禁止**静默降级——兜底声明化（ADR-039）在工具形态下原样成立（工具执行失败 = 结构化错误回执 + loop 内吸收或终态诚实失败）。
- **禁止**冻参模板当用户文案（ADR-058 二源律）；工具名永不上用户面（碎碎念 = 注册项的文案键，不是工具名）。
- **禁止**整段瞬移（打字机律在工具线格式下重述后仍是绝对规范）。
- **禁止**复读式收官（09-04 判词维持）——reviewer 说判断与引导，不复读 spec.summary。
- **禁止**动画布三族批在飞文件（§1 避让清单）。
- prompt 面改动必过 `scripts/prompt_gate.py`（ADR-071 T2）；零假设测试纪律（注册表条目扰动 prompt——条目从简 + 门禁枚举）。

## 4. 风险挂账（施工期盯防）

1. M3 多工具多轮择工具准确率（工具数 ~12 < Agno 实测 ~20 幻觉线；超标即砍工具合并同类）。
2. tool_calls 截断 ~11%（spike 实测）——工具错误反馈吸收；复跑升高即回查线格式。
3. 触发回合的主动性边界：白名单外永不主动说话；触发即唤回 dock 的打扰度走产品试用校准。
4. service.py 拆解期的行为漂移——以剧本测试全绿为每 commit 门禁。
