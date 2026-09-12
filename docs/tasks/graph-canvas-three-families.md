# 画布三族批（ADR-072）——施工简报

> Status: 已拍板待实施（2026-09-12）。拍板过程：画布走查三伤（锚线歪 / @ 锚 / PROMPT 参数回声）→ 画布公理讨论收敛 → ADR-072。
> 本文是实施的唯一工作简报；决策正文在 `docs/DECISIONS.md` ADR-072。完成后归 `docs/tasks/done/`。

## 0. 一句话目标

画布从「ElevenLabs 式技术流程卡」翻转为**物料流图**：源 → 文档（文字工作产品）→ 装配（媒体产物），每个元素必须回答「用户在这儿能知道什么、能改什么」；程序的本质决定卡面形态（散文程序挂用户原话 / 参数程序挂结构化杠杆 / 无程序无杠杆位）。

## 1. 先读清单（按序）

**文档**：
1. `docs/DECISIONS.md` **ADR-072**（本批全部判词）+ ADR-057（图即产品对象）/ ADR-058（二源律、通道分家）/ ADR-061（变体并行律）/ ADR-062（边对账律）/ ADR-067（端口法则）/ ADR-070（确认拍 dock）
2. `docs/CHAT_ARCHITECTURE.md` §5（物化）+ §8.5（提问机器）——§5 顶部有本批注记
3. `docs/AGENT_ARCHITECTURE.md` §3（概念表）/ §4（NodeBase + 图算法）/ §7（工具包）——§4.5 有本批注记
4. `CLAUDE.md` 的 Composer behavioral contract 段（端口法则 / 全文卡律 / 通道分家——ctx→T 折叠已落地）
5. `docs/RENDERING.md`（clip-spec 契约——本批不动它，但两站拆分的装配站最终都编译进 clip-spec）

**代码（后端）**：`apps/api/app/pipeline/graph_fill.py`（家族盖章 / fill_key / 边派生 §7 / 边对账 §7b）、`graph_store.py`（apply_wiring_ops 唯一写门 / `_TASK_BOOK_ROLE` / `_document_frame` / 画布定居取景）、`orchestrator.py`（compile_graph / `_compile_task_list` / create_run）、`node_runners.py`（preprocess / understand / plan / interrupt / render）、`tools/captions/node.py`、`tools/dub/node.py`、`tools/clips/node.py`（render fan-out 先例）、`tools/research/node.py`（有界 loop + brief 文档先例）、`pipeline/outputs.py`（`compose_spec_prompt`——本批退役）、`models/schemas.py`（TaskItem / IntentProposal / TaskSpec）、`app/prompts/chat/*.j2`（router 模板——prompt 面，动它必过 gate）。

**代码（前端）**：`apps/web/src/components/flow/`（FlowView / FlowNodeCard / FlowEdge / layout.ts / types.ts / ResultsCanvas.tsx）、`apps/web/src/lib/types.ts`（GraphNodeKind / GraphEdgeType）、i18n `locales/en.ts` 先行。

## 2. 终态形状（验收的参照系）

「Caption my video in Chinese and French — Chinese bilingual — and dub a Spanish version in my own voice」的终态画布：

```
视频源(asset) → transcript(散文档) → 中文字幕稿(表格档) → 中文字幕成片(装配)
                                 → 法文字幕稿(表格档) → 法文字幕成片(装配)
                                 → 西语配音稿(表格档) → 西语配音成片(装配)
```

clips 链：`视频源 → transcript → 分镜表(表格档) → clips 装配卡`。
writer 链：`素材 → transcript →（research brief）→ post/article(散文档，终态)`。

**画布上永不存在**：task_book 节点、materialize/preprocess/understand/plan/render/verify 节点、modifier 节点（music/filler/reframe）、ctx 边、@ glyph、参数回声 PROMPT。

### 三族卡面解剖

| 族 | 解剖 | 改点 |
|---|---|---|
| 源（asset） | 媒体本体 + factsbar（现状不动） | reprocess / 删除 |
| 文档·散文档 | 全文卡（封顶滚动 DOCUMENT_MAX_H 560 不变）+ 文字层直改 + （散文程序者）PROMPT 区 = 用户原话 | 改字 → 下游 stale |
| 文档·表格档 | 行 = 结构化条目，单元格级编辑 | 改格 → 下游 stale |
| 装配（assemble） | 媒体产物区 + **杠杆行**（≤3 已启用定义性参数）+ factsbar + 估价 | 翻杠杆（`set_param`）/ chat 散文 |

**表格档三成员**：译文 / 配音稿（行 = caption cue：时间窗 + 源文 + 译文列）与分镜表（行 = 分镜槽位：时间窗 + 论点 + 覆盖理由）。散文档四成员：transcript / post / article / research brief。

**杠杆内容**（首批）：字幕成片 = 双语开关 + 画幅；配音成片 = 声纹 + 画幅；clips 卡 = 画幅。样式参数永不上杠杆行（persona 皮肤 + 本批留 `style_overrides` 数据地基）。未启用的参数不上行（卡面不做能力货架）。

## 2.5 施工前取证清单（动手写代码前必须完成）

以下未知数**先取证、写成施工方案、用户确认后再动工**——不许边写边猜：

1. **plan 的分镜产物持久形态**：`node_runners.py` plan 节点（约 line 683 起）现在把分镜槽位/覆盖报告存哪（run.context？step spec？），能否直接物化为文档节点 spec；
2. **translate/dub 工序内部结构**：`tools/captions/`、`tools/dub/` 的 procedure 里翻译与摊铺/合成的接缝在哪，拆两站的切口取哪；
3. **家族分组机制**：graph_fill 的 `families` 如何从编译 steps 分组、fill_key 如何映射节点——一变二（文档站 + 装配站）的最小切口；
4. **graph 读面形状**：`GET /projects/{id}/graph` 的序列化在哪、legacy 五型行的过滤/映射加在哪一层；
5. **存量数据盘点**：dev 库里现有 graph_nodes 的 kind 分布、ctx 边数量、task_book 节点行数——决定读容忍的落实形态（滤除 vs 映射渲染）。

**流程闸**：复述终态理解 → 取证五问 → 施工方案（含每批 commit 切分）→ **用户确认** → 动工。

## 2.6 环境速查

- 后端：`cd apps/api && uv run uvicorn app.main:app --port 8000`（API）；worker = `python -m app.worker` 常驻认领——**改 pipeline 代码必须重启 worker**，否则旧代码抢跑新 run；
- 前端：`apps/web` 下 dev server；类型闸 `npx tsc --noEmit`；
- DB：migration 纪律见 `docs/DATABASE_MIGRATIONS.md`（Alembic，`migrations/versions/*.py` 随代码提交）——kind 词汇变更 / `style_overrides` 键 / 任何新列都走它；清部署用 `apps/api/scripts/reset_db.py`（dry-run 先看 banner）；
- 闸的位置：纯函数套 `cd apps/api && uv run --extra dev python -m pytest tests/ -q`；prompt 面改动后 `uv run python scripts/prompt_gate.py`；全量行为 `uv run python scripts/chat_scenarios.py`。

## 3. 批次切分

### 批 A — 管线拆分（先于一切）

1. **translate_clip 拆两站**：translator（共享 agent，现成）产出**译文 artifact**（行级 cue 结构：源文 + 译文 + 时间窗映射）持久化 → 文档节点（fill_key `translate_clip#<lang>#doc`）；摊铺 + 渲染归装配站（fill_key `translate_clip#<lang>#asm`）。一个 tool 不变（注册表与意图面不动），**家族盖章一变二**。
2. **dub_clip 同拆**：配音稿文档站 + 配音装配站（声纹参数挂装配站）。
3. **materialize_source 折叠**：编译注入不变（orchestrator 的 materialize_profile 逻辑保留），graph_fill 不再为它 stamp 节点，其 step 并入下游装配家族；边派生改为素材直连装配站（video edge）。
4. **估价归位**：文档站 = translator token 区间（编译期可报）；装配站 = render 报价（transform 链 mid-run NULL 的诚实面行为保持，ADR-063）。reuse 钩子：译文文档按（源文本 hash + 语言）命中复用（understand 的 asset-hash 先例），改字后重渲染**不再买翻译**（billing 对账可见 translator capture 为 0）。
5. **关键联动——配方对账自检**：AGENT_ARCH §4.2 的 ⊆ 对账（配方 flow keys ⊆ 编译图 kind 集）随新编译形状同步更新（`pipeline/recipes.py` 的 flow 声明与对账逻辑）。modifier 杠杆化与 materialize 折叠后编译图 kind 集变化，**这里不改会启动即红**。

### 批 B — 图模型

1. **task_book 节点下线**：graph_fill 拆除书节点 stamp（`book_newborn_id` 路径）；`pending_brief` / 出书门槛 / dock 全不动；draft confirm 的 dock pill 不动（卡内 confirm 随节点消失）。graph 读面（`GET /projects/{id}/graph`）滤除 legacy `role=task_book` 的 document 行（行保留，不展示）。
2. **ctx 边退役**：graph_fill §7 的 `connect(task_book_id, target, "ctx")` 删除；存量 ctx 边经边对账律（ADR-062 disconnect）在下一次 stamp 撤回——验证 disconnect 的 claimed 集合覆盖此路径。`GraphEdgeType` 的 `"ctx"` 保留类型读容忍，永不新写。
3. **分镜表表格档节点**：plan 的分镜产物（分镜槽位 + 覆盖报告）持久化取证（现行形态在 `node_runners.py` plan 附近，先查再造）；仅 clips 链（含 select_clips）stamp 分镜表节点，位置 = transcript 与 clips 卡之间；用户原话（`spec.instruction`）挂它头上；编辑映射：删行 = 弃选该槽、改时间窗 = 重切、改论点 = 重选——全部确定性 op。
4. **modifier 杠杆化**：add_music / remove_filler / reframe_clip 不再 stamp 节点；参数并入所属装配节点 `spec.params`；新 wiring op **`set_param`**（graph_store 写门加 op 类型；通道 = 既有 `POST /projects/{id}/graph/revise`，代码构建 ops，dock 零消息，程序区定价确认解剖复用）；受影响子图 = 本节点重渲染。
5. **kind 词汇三族化**：`graph_nodes.kind` 与前端 `GraphNodeKind` 改 asset / document / assemble 三值；legacy 五值行读容忍映射（generator/processor/agent → 按 output/frame_class 归族显示）。注意 graph_fill `_PROCESSOR_KINDS` / `_frame_class_of` 的归族逻辑随之改写。
6. **TaskItem.instruction（prompt 面，过 gate）**：`schemas.py` TaskItem 加可选 `instruction`（注意 `extra="forbid"`）；router j2 加规则「逐任务**逐字摘录**用户原话——copy verbatim，永不改写；用户没枚举子任务则 null」；compile 落 `spec.instruction`；graph_fill 盖章优先级 = `spec.instruction` → null（**`compose_spec_prompt` 显示职责整体退役**，函数可留作 legacy 行回退或删除，读容忍由 spec 缺字段天然承担）；无原话 = 程序区不渲染。run 级 `TaskSpec.instruction` 不上卡（用户的话在 chat 历史里，卡面不复读）。
7. **文档文字直改通道**：graph/revise 加 `edit_document_text` op（确定性、dock 零消息、卡面乐观回显）——适用 transcript / 译文 cue 译文列 / 分镜表格 / post / article。**两层诚实写死**：只动文字层，词级时间戳永远不动；时间轴错了的出路 = 素材 reprocess。改后下游级联 stale（现成机制：factsbar 「可重跑」徽）。
8. **样式覆写地基**：装配节点 spec 留 `style_overrides` JSONB 键（数据层 only，本批无 UI）。

### 批 C — UI

1. **锚点测量污染修复**（本批的原始触发伤）：`FlowNodeCard` 的 `flow-node-born` 动画容器不再包 `NodePorts`——root 静止、内容 wrapper 承担动画（或 `onAnimationEnd` → `useUpdateNodeInternals()(id)`，取前者）。验收 = CDP 实测出生动画完成后边插圆缘（回到 2026-09-10 圆缘贝塞尔判词状态）。
2. **三族卡组件**：FlowNodeCard 按新 kind 分流；装配卡 = 产物区 + 杠杆行（新组件，≤3，只渲染已启用参数）+ factsbar + 估价（无 ProgramRegion）；散文档卡 = DocumentCard 加直改（两解剖共用全文卡律 + 封顶滚动）；表格档卡 = 新组件（行解剖 + 单元格编辑）。
3. **ProgramRegion 收窄**：只挂散文程序文档节点，内容 = `spec.instruction`（用户原话），null 不渲染；卡面直改（K4 编辑 → 定价确认 → graph/revise）语义不变。
4. **frame 数学**：表格档行数驱动卡高（封顶 560 同律，server `graph_store._document_frame` ↔ client `layout.ts` 一条测量律两镜像互引——禁止第三份拷贝）；装配卡杠杆行高度纳入预留（geometry never shifts）。
5. **i18n**：新文案 en.ts 先行、zh.ts 镜像（`zh: Resources` 类型闸）；言语语言律不变。
6. **RecipeInspectOverlay / 配方说明书面**：不动（untyped surface 保留 legacy 隐形 handle 对）。

## 4. 不变量（本批不许碰的机制）

compile_graph 纯函数与确定性（同一编译 → 同一 fill_key → draft 原地填充无双生）/ `apply_wiring_ops` 唯一写口 / `create_run` 唯一出生地（新入口校验归它）/ 边对账律 / billing 三缝合点（hold→capture→release）/ 变体并行律 / SSE 打勾流与打字机律 / 单一渲染面律 / 双引擎分离（对话永不编译进 DAG）/ 提问机器与 dock 三形态机 / L3 铁律（无多轨时间线）。

## 5. 验收

- **场景主线（multilingual-subs）**：新项目发那句英文 → draft 图 = §2 终态形状；无书节点 / 无 ctx 边 / 无 @ / 无 Prepare 卡；文档站编译期有报价；Start → run 原地填充；**译错字 → 改译文 cue 单元格 → 装配卡 stale → 重渲染且 translator 零 capture**（billing 明细实证）。
- **clips 链**：分镜表节点在 transcript 与 clips 卡之间；删一行 → 重选后该条不再出现；count 步进器行为不变。
- **杠杆**：字幕成片卡翻双语开关 → 定价确认 → 零 dock 消息 → 卡面重渲染。
- **PROMPT**：writer 节点挂用户原话分片；transform 链（无枚举原话）程序区不出现；legacy 行（旧 composed prompt）正常回退显示。
- **legacy 读容忍**：旧项目（五型行 / ctx 边 / 书节点行 / 旧 composed prompt）打开零 crash。
- **启动自检**：配方对账 ⊆ 绿；`assert_runners_registered` 绿。
- **闸**：`cd apps/api && uv run --extra dev python -m pytest tests/ -q`（纯函数套，含本批新增）→ `uv run python scripts/prompt_gate.py`（三探针绝对阈值，判负复跑一次再 bisect，**永不调阈值迁就**）→ 全量 `scripts/chat_scenarios.py`；前端 `npx tsc --noEmit` 零错。实况走查（CDP 截图 / 产品试用）归用户。

## 6. Prohibited Behaviors

- **禁止**第四族 / 新卡种 / generator 卡复活——三族之外无画布节点。
- **禁止**参数回声复活（compose_spec_prompt 式拼装行）——程序区只有用户原话或不存在。
- **禁止** LLM 改写/润色用户原话分片——摘录必须 verbatim（prompt 里写死）。
- **禁止**卡面能力货架——未启用参数不上杠杆行；样式不上杠杆行。
- **禁止** task_book 节点任何形式复活；确认拍唯一座位 = dock。
- **禁止**绕开 `apply_wiring_ops` / `create_run` / graph/revise 通道的写路。
- **禁止**文档改字动时间轴层（词级时间戳只读）。
- **禁止**手动布线 UI / 添加节点菜单（MiniMax 三不抄，ADR-072 判词 12）。
- **禁止** prompt 改动不过 gate；禁调探针阈值迁就回归（ADR-071 T2 仪式）。
- **禁止**新增工具绕过注册表扩展门（一个包一条 import，全家桶随登记免费获得）。
- **禁止** frame/高度数学出现第三份拷贝（server mirror ↔ client layout 互引）。

## 7. 收口义务（实施完成后）

1. `CHAT_ARCHITECTURE.md` §5 与 `AGENT_ARCHITECTURE.md` §4.5 的本批注记改写为现在时正文（文档卫生：过时内容删除，历史在 git）；`DIALOG_WORKFLOW.md` §2.2 的 ADR-057 注同改（任务书不再并入图感知层）。
2. `CLAUDE.md` 画布段同步（节点五型 → 三族、杠杆行、表格档、书节点下线）。
3. PROGRESS 本批行记交付明细；遗留（quotes/carousel 两站拆分、样式覆写 UI、分镜表 rev 迭代）入需求池。
