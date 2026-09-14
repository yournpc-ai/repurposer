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

5. **kind 词汇三族化**：`graph_nodes.kind` 与前端 `GraphNodeKind` 改 asset / document / assemble 三值；legacy 五值行读容忍映射（generator/processor/agent → 按 output/frame_class 归族显示）。注意 graph_fill `_PROCESSOR_KINDS` / `_frame_class_of` 的归族逻辑随之改写。（**2026-09-14 ADR-076 改写本条**：列改名 kind→type，值 = 媒介五值 text/table/image/video/audio + `spec.prototype` 三值 generator/editor/manual——按 §3.5 词表 v3 执行，三值 asset/document/assemble 案作废。）
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

## 3.5 实施计划（2026-09-14 评审修订 + 词表 v3 拍板——commit 级批次的唯一真相）

> §3 的 A/B/C 保留为概念地图；批次切分以本节为准。词表 v3 决策全文 = **ADR-076**。本节的评审修正来自对 HEAD=`4e41caf` 的全码核对（行号以该 commit 为基准，漂移以义不以数）。

### 3.5.1 词表 v3 速查（ADR-076）

- **三轴**：`type`（graph_nodes 列，kind→type 改名）= `text`/`table`/`image`/`video`/`audio` 五媒介值；`spec.prototype` = `generator`/`editor`/`manual`；业务身份 = `spec.summary`（label）+ `spec.tool`（执行体）。解剖 = type 直出（text→全文卡、table→表格卡、image/video/audio→媒体卡），程序区 = prototype 直出。
- **NodeBase 声明换装**：`family` → `node_type`（媒介值）+ 新增 `prototype`；`doc_station` 保留（其文档站恒 type=table、prototype=manual）。orchestrator 启动自检同批追齐。
- **端口表**（graph_store `_NODE_PORTS` → 按 type(+prototype) 重写）：video 恒 offers {video,audio,text}；text/table offers {text}；image offers {image,text}；accepts 按 prototype 分（editor 收媒介+text、generator 收 text、manual 不收）。legacy 五型条目保留做读容忍（旧行连线仍要过门）。
- **EditPromptOp 闸门**：终态 = `prototype=="generator"`；**过渡期保持 spec.tool 存在性**（批 B4 set_param 落地前 editor 修订不断粮）。
- **`spec.role` 保留为内部出生证**（transcript 级联删除 / task_book +88 框架额 `_DOCUMENT_CONFIRM_PX`），不驱动卡面身份，批 B1 收编。
- **`spec.frame_class` 退役**：框架律直读 type（旧行 frame_class 留作读容忍回退）。

### 3.5.2 已落地（勿重做）

| commit | 内容 |
|---|---|
| `737faa8` | 批 A1：译文 cue 表接缝纯函数化（`tools/captions/procedure.py` build_translation_cues/spread/unit + dub 同款） |
| `f73f29f` | 批 A2：译文 artifact 持久化（`spec.translation` = {clips:{output_id:{source_hash,title,rows}}}，译文文本永不入哈希）+ `find_reusable_translation` 复用钩 + `merge_translation_artifact`（own-session jsonb_set，D9 纪律） |
| `086cdc2` | 批 A3 前置：NodeBase family/doc_station 声明落 14 节点 + orchestrator 自检断言（**属性名随词表 v3 换装 node_type/prototype**） |
| `8b7d6bc` | 批 C1 提前：锚点测量污染修复（born 动画移出节点根） |
| `8249bdd` | 多版本变体自动 fork（tracks.py autofork_parallel_variants，compile 期） |
| `a82e1a9`/`ce0ae2e`/`f194672` | 演示冻结期读面 lite 补丁（全在 `routes/projects.py:get_project_graph`）：B1-lite 滤 task_book / B4-lite 滤 morph modifier（surviving_claims 保守闸门）/ A3-lite 合成 transcript→消费者 text 边（orm_edges 一次性快照防自迭代 500）。正式批转生产面后**保留作旧数据容忍** |

另：ADR-073/074/075 三批（09-13）已落——消息流时序 / 部分失败=FAILED / 渲染撑 run / 画布几何零测量依赖（rfNode 三件套 + declaredHandles）/ 产物跟源比例分档加宽 / 卡面直改暂停（b367e94：ProgramRegion 编辑入口 onClick 注释化，链休眠但完整，唤醒只需恢复 onClick）。

### 3.5.3 批次（顺序强依赖，每 commit 自绿）

**C1 — 前端休眠兼容**（零行为变化；此时服务端还没产新词）✅ 已落 `1a2547e`
- `lib/types.ts`：`GraphNodeKind` 并集加新值（过渡）；`flow/types.ts` 同步。
- 卡分流点全部改为「spec.type 优先、kind 推导兜底」或加并集：FlowNodeCard.tsx 分流（现 1732 `isGraphCard`）/ FlowView.tsx `productionPort`（42 行——新 type 直接按媒介出锚，天然兼容，只需确认 fallback）、ResultsCanvas.tsx draft 过滤（499）与 blast 估价过滤（602）。
- `layout.ts`：尺寸双轨（FLOW_NODE_SIZE fallback + graphNodeSize 内容驱动）都加新 type 分支。
- editable 闸门（FlowNodeCard.tsx:1543）改 spec.tool 存在性（直改暂停期只影响 hover wash 诚实）。
- i18n 先行（休眠键）：type 五值的 fallback 标签 + prototype 相关键，en.ts → zh.ts 镜像。
- 绿：`cd apps/web && npx tsc --noEmit` 零错。

**C2a — 写门门层先行**（零 stamp 行为变化）✅ 已落 `6d24a4f`
- graph_store：`AddNodeOp.kind` 校验从五值 Literal 放开（新 type 值 + legacy 五值容忍——可改注册表驱动）；`_NODE_PORTS` 按 type(+prototype) 重写并保留 legacy 五型条目；**document/text 类型 accepts 过渡性含 ctx**（任务书→writer 的 ctx 边否则令整 stamp 批 422——本批最高危交互点，显式测）；EditPromptOp 闸门改「spec.tool 存在 或 kind∈(generator,agent) 旧行兜底」（无 tool 的文档恒拒）。
- **graph_revise.py:46**：`task_for_graph_node` 的跳过规则从 `kind in ("asset","document")` 改为「asset 或 无 spec.tool」——writer 升 text 型后 chat 修订 run 桥不断（**评审修正 P0-B**）。
- 门层测试三族化 + legacy 容忍用例。
- 绿：pytest 全绿。

**C2b — stamp 核心三族化（本批重心）** ✅ 已落 `f9c667f`
graph_fill.py：
- **退役 `_graph_kind_of`**（1108-1114）：判族改读 `NODE_KINDS[step.kind]` 的 node_type/prototype 声明（materialize_source/align_stills/revise_script 的 fold-into 语义保留；revise 折叠处 624 行硬编 "generator" 改读目标族）。
- **两站 stamp**：doc_station 非空的 kind → asm 族（type=video，prototype=editor）+ doc 族（key=`{fill_key}#doc`，type=table，prototype=manual，spec.role=doc_station 值）。**机制细则**：doc 站不走通用 family 循环（空 steps 会炸 `fam_steps[0]`、§6 回填循环会把 step.spec.graph_node_id 错指 doc）——asm 族 stamp 时预生 doc pinned id（任务书 743 行同款先定后连），doc 节点在 companion 块 add（无 tool/prompt/step_ids），asm.spec.doc_node_id 写入含 reused 分支；§6 回填循环只认 asm 族。
- **materialize 折叠**：不再自建族；fold map 复用 revise_target_keys 先例——folded 步的 `node_of` 返回 None（align_stills 现成先例：bare fill key 不建族即天然跳过）；root 判定改为「clip 族上游且 node_of(upstream) 非 None 且 ≠ 我」。**评审修正 P0-C**：`_SOURCE_CONSUMERS` 不可按 kind 收缩——materialize 只在 media/stills profile 注入（mode② existing 不注入，orchestrator:460-477），吸收了 materialize 的宿主 root **必须继承「恒吃素材」语义**，否则老项目有既有 clips 时整源链错接旧 producer（画布撒谎）。
- **research 塌缩**：单节点（type=text，prototype=generator，fill_key="research"，spec.tool="research"）；删 §6b brief 文档创建（881-910）、brief_doc_id 回写（1080-1097）、orphan-sweep 特例（679-684）、sync agent 镜像（1292-1301）；sync 直渲 step.spec.research_brief → 节点 spec.text（`_research_brief_text` 复用）。writers 经通用步 input 回路（consumes_research 接线 orchestrator:444-447）自动接 research 文本边。
- **write_post/write_article 升 text 型**：prototype=generator；spec.tool/prompt/params 保留；sync 增回写——新 output_refs 落地时读最新 Output（`Output.workflow_step_id` 直查先例，单步单行不变量由 derivative_dispatch 的 sweep 维持）写 spec.text = payload.content。
- **评审修正 P0-A**：prompt 组合闸门（现 790 行 `if fam["kind"] in ("generator","agent")`）必须随词表改判——`#doc` 族恒跳过（文本站无 prompt 位，ADR-072③），其余照旧 `compose_spec_prompt(head) or instruction or query`（compose 本体 B5 才拆，本批不动）。
- **边派生新规**：transcript→译文稿/配音稿（text，按 asset_id 找 transcript 文档——A3-lite 的读面合成转生产面，但 transcript→成片的直连边不再合成，文流经 doc 站中转）；译文稿→asm（text）；asset→asm（video，由折叠后的 root 逻辑给出）。§7b claimed 集含 doc 节点，旧边对账自然覆盖。
- **sync 双站**：asm 节点照旧聚合（step 指 asm）；尾部读 asm.spec.doc_node_id → doc 节点镜像 state + 从 doc.spec.translation.clips 渲染 spec.text（每行 `start–end text`）。
- graph_fill 模块 docstring 的 migration mapping 段（31-37 行）改写现在时。
- runners：captions/node.py:135 与 dub/procedure.py:74-114 的 artifact 目标——解析 asm.spec.doc_node_id 得 doc 节点；**读 = `doc.artifact or asm.artifact` 回退**（迁移边界零重买翻译），**写 = 只写 doc**。merge_translation_artifact 签名不变（按目标 id 参数化）。
- 测试（test_graph_wiring_pure.py 同 commit 改写保持绿）：端口/门三族化 + legacy 容忍（旧五型行 ↔ 新节点连线派生仍通）；fill_key 三形态补 `#doc`；两站 stamp（asm+doc、doc_node_id、doc 无 tool/prompt/step_ids）；materialize 折叠（无节点、step id 入宿主、宿主 root 恒吃素材、素材直连边）；research 单节点（双节点锁定用例重写）；writer spec.text 回写；任务书 + _document_frame 数学不动。
- 绿：pytest + 冷启动 assert_runners_registered（family→node_type/prototype 自检追齐）。

**C3 — 批 A4 两站估价归位（评审修正 P0-D：stamp 侧拆分，step.estimate 一律不动）** ✅ 已落 `51a7f86`
- 事实基础：translate 的 estimate 现就是纯 translator token 报价（captions/node.py:75-97，无 render 成分）；fan-out render 全 NULL（ADR-063 诚实面），render_seconds 零定价；dub = estimate_mechanical 混合体（token 段 + units 段 tts_chars/voice_clones）。
- 切口 = `_family_estimate` 层 token/units JSON 分拆：doc 族 = token 段（translate 全量、dub 的 prompt/completion 段），asm 族 = units 段或 None（translate 的 asm 编译期 None =「估价随运行」；voice_clones 归 asm——配音产物的声纹单位）。
- **铁律**：create_run 的 hold fold 的是 step 级 estimate（orchestrator:1059）——step.estimate 零改动，hold 不变性测试锁定；fold_estimates 计量钳制（voice_clones min-1）不动。
- 绿：pytest（两站各归其座 + reuse 时 doc 站 capture 0 账面 + hold 不变性）。

**C4 — 写门收窄 + 读面映射（prompt 面 → gate 用户代跑）** ✅ 已落 `34ada59`（prompt gate 归用户代跑）
- AddNodeOp 校验收窄到 v3 词表（注册表驱动：五媒介值 + 注册表声明）；`wiring_catalog_lines` 同步改写（**prompt 面 → `scripts/prompt_gate.py` 必过，判负复跑再 bisect，永不调阈值迁就**）。
- `get_project_graph` 加纯函数 `_read_face`（可纯测）：legacy 行映射——asset→asset_type 媒介值+manual；document+role=transcript/task_book/research_brief→text；generator/processor/agent→按 spec.tool 落（writers→text+generator 且 spec.text 从最新 joined output payload.content 合成；quotes/carousel→image+generator；clips/translate/dub→video+editor；modifier→modifier 旧词；materialize→materialize 过渡词）；新行直传。键用 spec.tool 而非裸 kind——兜 C2b 后 reused 旧行的 kind 错位（fill_key 不变 → 重盖章复用旧行，列值不迁移，读面映射兜底；草稿重 dock 的 orphan sweep 最终收敛）。
- 三 lite 补丁保留作旧数据守卫。
- 绿：pytest + 冷启动 + prompt gate。

**C5 — 前端收窄** ✅ 已落 `0bc56f2`
- `GraphNodeKind`→ 新词表联合（或改名 GraphNodeType 随 C5b）；卡分流按 type + prototype（text→DocumentCard、table→暂走 DocumentCard 全文渲染（TableCard 归 UI 批）、媒介→GraphCard 路径）；程序区按 prototype 门控——**editor 卡的 prompt 区显示提前退场**（compose 回声显示侧不等 B5）；ResultsCanvas 过滤改 prototype/card 语义；清 draftTaskCount 的 materialize 死过滤。
- **DocumentCard 最小产物尾（2026-09-14 已拍板）**：output_ids 非空时底部一条 factsbar——版本 pager + copy/download + 打开 inspector；选区引用 pill 不做（归 UI 批）。
- 绿：tsc 零错。

**C5b — 列改名 kind→type** ✅ 已落 `3d43815`（prompt gate 重跑归用户代跑）
- Alembic：`graph_nodes.kind` → `type`（列改名；值已在 C2b/C4 就位，本步无值迁移）；ORM + 全栈读点 + 前端 GraphNodeType 终名 + wiring_catalog_lines 的 `kind:` 词（prompt gate 重跑，用户代跑）。
- 绿：pytest + 迁移幂等 + gate。

**C6 — 画布相机批（2026-09-14 拍板排入）** ✅ 已落 `c7031a7`（间距拍板 64/16/88；replay 迁移拍板不做；实况走查归用户）
- **聚焦转场**：FlowView 监听节点 id delta，仅用户发起节拍触发——chat 发送后 draft 图到来 = 整链 fit（复用 ViewportController settle framing）；会话中途新节点诞生 = `setCenter(x+w/2, y+h/2, {duration:~500})` **保持当前 zoom 只平移**。护栏：手势防护（用户近期拖/缩过则不抢——2026-08-19「explore 面增长不动视口」拍板的收窄不是推翻）、docked 几何面板遮挡补偿（onPanelStateChange 先例）、prefers-reduced-motion 退化瞬移、背景 refetch 永不触发。
- **俯视 discoverability**：比例尺 pill 加回 fit icon（2026-09-05 瘦身拍板后「点击百分比=fit」是隐形知识）。
- **间距常数收紧**：server graph_store `_GAP_MAIN`(96)/`_GAP_CROSS`(24)/`_FRESH_COLUMN_RISE`(126) ↔ client layout.ts 一条律两镜像同批改；只影响新出生帧（append-only 保序律不动）；旧项目可选 replay 迁移（e7a9c1d35b28 先例）。不引 dagre/elk（禁第二布局律）。
- 绿：tsc + 用户实况走查。

### 3.5.4 评审修正四条（动工必带）

| # | 位置 | 问题 | 修法 |
|---|---|---|---|
| P0-A | graph_fill.py prompt 闸门（790） | 按五型判定，三族化后 compose 全灭（B5 前 prompt 必须继续盖章） | `#doc` 族恒跳过，其余照旧 compose/instruction/query |
| P0-B | graph_revise.py:46 | task 桥按 kind 跳 document——writer 升 text 型后 graph/revise + chat 修订 run 桥 422 | 跳过条件改「asset 或 无 spec.tool」 |
| P0-C | graph_fill.py `_SOURCE_CONSUMERS`（988） | 按 kind 收缩会在「老项目有既有 clips + 新整源链」时把宿主 root 错接旧 producer | fold map 驱动：吸收了 materialize 的宿主恒吃素材 |
| P0-D | 批 A4 估价 | translate estimate 纯 translator token（无 render 成分可「保留」）；fan-out render 全 NULL | stamp 侧 token/units 拆分；step.estimate 不动保 hold |

### 3.5.5 机制细则备忘（C2b 施工时照此落）

1. **#doc 族空 steps 炸点**：`fam_steps[0]`/`_family_estimate`/§6 回填循环都要求族有 steps——doc 站走 companion 块，不进通用 family 循环。
2. **fold 机制 = revise_target_keys 同款**：folded 步（materialize/align_stills）的 `node_of` 返回 None 即天然跳过 step-input 边循环；root 判定忽略 folded 上游。
3. **runner artifact 迁移期读回退**：旧 translate/dub 节点的 artifact 在 asm 上，新写入指向 doc——读 `doc.artifact or asm.artifact`，写只写 doc；迁移边界零重买。
4. **dev 库盘点实况（2026-09-14）**：generator×20 + processor×5（materialize×4+reframe×1）+ document×21（transcript×10、task_book×11）+ asset×11；agent×0、research_brief×0（research 塌缩的旧数据容忍 dev 无样本，纯测试兜住）；ctx 边×11。
5. **writer 升 text 型的过渡形态**：post/article 卡从 GraphCard 转 DocumentCard 后失产物分页/发布动作——C5 最小产物尾补齐（已拍板）；/results 页动作全程冗余在。
6. **draft 估价总额**：doc+asm 两站拆分后总额不变（token 段+units 段=原整份），dock 确认拍的 fold 不破。


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
