# B4 施工简报——有界 loop 节点 + research 试点（ADR-052，DIALOG_WORKFLOW §2.6）

> Status: 待开工（简报 2026-09-03 落，排期 PROGRESS W7）。前置 = B1 ✅ / B2 ✅ / B3 ✅（d389880）。
> 本批是**架构批**：agent 性（多轮自主调工具）第一次获得合法座位——图内核的一个新节点类 + 它的第一个实例。三护栏是交付物本身，不是可选项。

## 1. 蓝图判词（DIALOG_WORKFLOW §2.6 复述）

agent 性合法化的唯一形态 = **有界 loop 节点**：NodeBase 子类，run() 内部驱动一个迷你工具循环（工具 = `app/tools/` 注册表能力），三护栏缺一不可——

1. **迭代上限**：`max_iterations` 类属性声明（试点 = 8），循环永不能超过它的报价；
2. **报价 = fold**：`estimate()` = 单次报价 × 上限，run 的 fold 天然计入最坏情形；
3. **对外 = DAG 单节点**：topology / roster / SSE 零改动，循环的迭代只投影到自己 step 的 summary，永不投到图上。

开放自治（steering / compaction / 自由 tool-loop）维持常备否决，本批不开门。

## 2. 变更表（蓝图片段 → 实现物）

| 蓝图 | 实现物 | 层 |
|---|---|---|
| 有界 loop 节点类 | `graph.py: BoundedLoopNode(NodeBase)`——`max_iterations: int = 8` 声明 + `loop_estimate(ctx)`（子类实现单次报价）+ `estimate()` 内核 fold（低高界与 units 全乘上限，未来 loop 节点想报错价都报不了） | graph 内核 |
| research 试点节点 | `app/tools/research/` 包：`node.py`（ResearchNode(BoundedLoopNode)，kind="research"，needs_plan_prelude=False，produces_outputs=False，requires=()，retries=0）/ `agents.py`（researcher: Agent[ResearchVerdict]）/ `params.py`（ResearchParams{query, angle?}）/ `web.py`（零键 web 对：web_search + fetch_text）+ `app/prompts/research.j2` | tools 包 |
| 迷你工具循环 | node.run() 内：每迭代一次 researcher 裁决（search/fetch/brief）→ 执行一个 web 工具 → 证据累积；`brief` 裁决或上限耗尽收尾。末次迭代 prompt 强制关门；仍不收尾 → 代码从已收证据机械合成 caveated brief（零额外 LLM 调用） | tools 包 |
| 三护栏 ③ 的拓扑 | 编译期提升（align_stills 先例）：research 从 chain 抽出，prelude 之后以 `inputs=[]` 插入（与 ASR/plan 并行——网络 bound 循环不吃计划关键路径）；writer 经声明式 `consumes_research = True`（DerivativeWriterNode 类属性）接线 `inputs=[plan_idx, research_idx]` | orchestrator |
| 研究 → writer 注入 | DerivativeWriterNode.run()：`collect_asset_texts` 之后追加同 run research steps 的 `spec.research_brief` 格式化块（provenance 头行先行，四 writer 全覆盖，零模板改动） | derivative_dispatch |
| 诚实降级 | research = 尽力增强，永不为阻塞：MiniMaxError / 搜索全灭 / 上限耗尽 → step 以 caveated brief 完成（"research unavailable" 自述），run 继续。**run() 对研究侧失败永不 raise**（DB/系统错误除外）；retries=0（重试 = 双倍 web 调用换同样的空） | tools 包 |
| schemas | ResearchSource{title,url} / ResearchBrief{summary, key_facts[], sources[], caveat?} / ResearchVerdict{action: search\|fetch\|brief, query?, url?, brief?}（extra=forbid） | schemas |
| 注册表条目 | `TOOL_REGISTRY["research"]`：description 从简 + 门禁（仅当请求点名调研/事实核查/时效性，或主题具时效性；常青稿不调研——prompt-perturbation 纪律：条目扰动即 prompt 扰动）+ summary_templates 双语 | tools/__init__ |
| 步骤行 | task_name "Research"/「调研」（builder-written pending 行）+ `results.stepper.researching` i18n（en "Researching the topic…" / zh「正在调研…」）+ 完成行 `_fill_summary`（{n} sources） | graph + i18n |
| spec 钢印 | `spec.research_brief` 经 `_set_spec_field`（own-session jsonb，D9 纪律——runner 永不脏 Session-2 节点） | step_display 复用 |
| harness S53 | chat 出书 → 改 chain 为 [research, write_post] 起步（S16 的 intent-edited start 先例）→ 等终态 → 断言 research step done + spec.research_brief 钢印 + post 产物存在（确定性 chain，活 DDG——网络降级时 brief 带 caveat 也算过，断言只看「钢印存在 + 产物存在」不看内容质量） | scripts |

**不在本批**：search provider 密钥化（DDG 零键试点先行）；research → clips/storyboard 注入（只喂四 writer）；多个 loop 节点（driver 上提等第二个实例出现）；画布产物卡（research 折进过程脊——过程动词无卡，既有律）。

## 3. 拓扑细案（编译期提升）

现状两个坑（已取证）：① `not needs_plan_prelude and not produces_outputs` 的节点会落 **modifiers**（整条链之后跑，orchestrator.py:347）——research 两头都不是，不能走这路；② 生产节点 `inputs=[plan_idx]`（:389），writer 群 plan 后并行——research 插进 chain 当普通节点会错序。

解法 = align_stills 先例（:343-346 抽出、:390-395 注入）的一般化：

1. 主循环**前**预扫 chain 抽出 research 任务；
2. plan_idx 定下后立刻注入 research 节点（`inputs=[]`——就绪判定对空 inputs 立刻可认领，jobs.py:93 已取证；seq 落在 plan 与 writer 之间）；
3. 主循环跳过 research（`continue`，必须在 modifier 分支之前）；
4. 生产节点接线处：`consumes_research` 为真且 research_indices 非空 → `inputs=[plan_idx, *research_indices]`。

语义不变量：chain 里 research 的位置无关（LLM 点名的位置不改变执行拓扑——对齐 align_stills 哲学「LLM naming it explicitly changes nothing」）；多 research 任务 = 多节点，writer 全接；无 writer 的 research chain 合法（简报进 step spec 无人消费，无害）。

## 4. Commit 切分

- **B4-C1 一批一 commit（自绿）**：BoundedLoopNode 内核 + research 包（node/agents/params/web/prompt）+ schemas + 注册表 + orchestrator 提升接线 + writer 注入 + i18n + S53 + docs（MODULE_ARCHITECTURE 代码地图 + AGENT_ARCHITECTURE BoundedLoopNode 段）。单 commit 理由：内核类、节点实例、编译接线三者互为依赖，拆开各自不可引导（startup self-check 走 node→agent 引用，半个包起不来）。

## 5. 验收

1. **三护栏结构在**（硬条）：max_iterations 声明在内核类上；estimate() = 上限 × 单次（S53 或既有 estimate 场景断言 fold 放大）；对外单节点（roster / SSE / FlowView 零改动——research step 就是任务列表里普通一行）。
2. [research, write_post] 零素材可编译可跑通（requires=() + 2026-08-24 writer lift），research 先于 writer 完成（inputs 接线保证）。
3. writer 的 asset_texts 末尾带研究简报块（provenance 头行）；无 research 的 run 的 writer 输入逐字节不变。
4. **降级诚实**（硬条）：DDG 全灭 / LLM 全灭时 run 仍 completed，research step done 且 brief 带 caveat 自述；research.run() 对研究侧失败零 raise。
5. 循环有界：最多 max_iterations 次 agent 调用 + 末次强制关门；代码合成兜底零额外调用。
6. S1~S52 无回归（剧本测试 全绿，用户自跑）。

## 6. Prohibited Behaviors

- **禁开放自治回潮**：不引入 steering / compaction / 自由 tool-loop / 运行期工具发现；循环的工具集 = 节点代码里的固定对（web_search / fetch_text），agent 只能选动作不能造工具。
- **禁新 DAG 形态**：loop 迭代不得产生新 step / 新 canvas 节点 / 新 SSE 事件类型；进度只走既有 spec.summary 通道（假进度禁令同在——不许编分数）。
- **禁阻塞化**：research 失败拖死 run = 架构事故；run() 不得把 MiniMaxError / httpx 错误抛给 worker（DB/系统层除外）。
- **禁模板改动**：writer 注入只动 asset_texts 装配层，四个 writer 的 j2 模板一行不动。
- **禁 provider 密钥**：本批 DDG HTML 零键试点；引入付费搜索 API 是另一批的决策。
- **禁 LLM 簿记上卡**：research_brief 进 step spec（机器通道），不进 brief 账本（对话引擎状态）——两个 brief 同名不同物，账本五槽永远不含 research。
