# 图内核重建批施工简报——图即产品对象（ADR-057）

> Status: ✅ 已落地（简报 2026-09-07 落；K1~K5 全部收口 2026-09-08——K1 两表 + wiring 层 / K2 run 图填充双写 / K3 `/graph` 直读 + runFlow 火化 + 节点卡重构 + 端口法则 / K4 prompt 直改 + 定价确认 + 修订 = edit_prompt+子图重跑 + 语义账本塌缩 / K5 草稿图 + 任务书 document 节点化 + 确认节点锚定 + 剧本 wiring 断言 + 文档现在时）。**K5 形态裁定**：dock 任务书卡（评审卡 + 确认 pill）在桌面 panel 形态退役——确认节拍由画布草稿确认卡（锚任务书 document 节点）接管；移动端无画布（禁令 #13）保留 dock 全套。验证（tsc / 剧本 / 产品试用）由用户自跑。
> 本批是**架构批**：图从「每次 run 编译即弃的产物」升正为**持久可变产品对象**。执行内核零改动是交付物本身，不是可选项；修订环根治（「Target clip not found」类伤口根灭）是验收硬条。

## 0. 开工前必读（新会话导读——本批假设零产品上下文）

按顺序读，每份都带着问题读：「这张图现在是谁、归谁写、谁在展示它」。

1. `docs/README.md`——docs 索引与治理原则（单一事实源表；哪份文档管什么）。
2. `CLAUDE.md`（仓库根）——前后端约定、组件纪律、队列纪律、commit 规范。其中的 Composer / 画布 / dock 段落描述的是**现状形态**，本批会改它涉及画布数据源的部分，其余纪律（rounded-full 例外 / overlay-surface / i18n / SSR / Tailwind token）全部继续有效。
3. `docs/MODULE_ARCHITECTURE.md`——六层模块图 + **表归属契约**（§4，新表已登记 `graph_nodes`/`graph_edges`）+ §7 代码地图 / 队列机制 / 数据约定。
4. `docs/DECISIONS.md`——**先读 ADR-057（本批母决策，含翻案表与节点五型表）**，再按需读它翻案的 ADR-036 / ADR-041 D5 / ADR-051 条款 2·4，以及存活的 ADR-039（NodeBase 四算子）/ ADR-043（整条源规则）/ ADR-052（brief 账本、有界 loop）/ ADR-055（计费内核）。
5. `docs/DIALOG_WORKFLOW.md`——厚 agent 蓝图：双引擎分离 / brief 账本 / 提问机器；§2.2 有 ADR-057 修订注（接口载体 = 持久图，任务书 = document 节点）。
6. `docs/CHAT_ARCHITECTURE.md`——chat 层现状行为规格（book path / 四态 / SSE / 打勾流）；§5 / §9 有本批重构注。
7. `docs/BILLING.md` §7——展示面四面 + 节点锚定确认 + 语义账本塌缩。
8. 本简报全文。原型 `scratch/node-ux-proposal.html` 是**形态对照件**（三场景：A 草稿态跑全图 / B 孤岛生长 / C 直改修订）——解剖与交互以本简报为准，不走 React 直译。

代码侧现状关键文件（文档读完再看）：

- `apps/api/app/pipeline/orchestrator.py`——`create_run`（WorkflowRun 唯一出生地，零旁路原则）+ billing 调用点（hold_run / capture_step / release_run）。
- `apps/api/app/pipeline/graph.py`——NodeBase 协议 + BoundedLoopNode + 图算法（报价=fold / 执行=topo / 校验=∀ / 对账=⊆）。
- `apps/api/app/tools/`——能力注册表（每个工具包 = 节点类 + params + 私有工序 + 估价 + 私有 agent 声明），未来 generator/processor/agent 节点的执行本体。
- `apps/web/src/components/flow/runFlow.ts`——**本批整体退役**的投影适配器（五补丁：`canvas_hidden` / `canvas_key` / 过程脊 spine / 脊收编 / R1 下游游走 `resolveAssetFeedTargets`）。读它是为了理解旧投影在藏什么，不是为了修它。
- `apps/web/src/components/flow/types.ts` + `FlowNodeCard.tsx`——节点卡现状（Handle 不可见 `!h-0 !w-0 !opacity-0`；caption / StepCard / SpineCard / ArtifactCard / ProductCard）。
- `apps/web/src/components/results/OutputInspector.tsx`——产物档案面板（出生证明 + 估价/实扣对账尺——节点卡 factsbar 的信息源）。
- `apps/web/src/components/credits/CreditsPill.tsx`——积分 pill（语义账本塌缩的改写点）。
- `apps/web/src/components/chat/ChatDock.tsx`——chat 三形态机（confirm 消费点 / 灰行 / 打勾流）。

## 1. 蓝图判词（ADR-057 复述）

**图 = 持久可变产品对象**。从「chat 确认任务书 → 编译一次性图 → 画布投影它」翻案为：

```
chat 建/改持久草稿图（wiring ops）→ 确认（节点锚定 + 估价随行）→ run 填充节点 → 修订 = 原地图变更
```

- **wiring 层** = 图变更 API：`add_node` / `connect` / `edit_prompt` / `delete_node` / `run(_subgraph)`。chat 是唯一消费面；**能力完备、手势缺席**（手动布线功能必须完善——chat 布线的表达力以它为底；UI 永不开放手动）。
- **初始生成 / 修订 / 新建 = 同一组 wiring op**——「修订环」一词退役；孤岛合法（图 = 森林）。
- **执行内核零改动**：`workflow_steps` 保持 step 粒度（billing capture / 计量 / 重试靠它），steps 住进节点**内部**作为节点的内部 workflow——组合，不是投影。
- **投影层火化**：五补丁连根拔——显示模型 = 领域模型，画布直读图，零适配投影。
- **首站 = 现有管线迁移上图**（本批全部工期）；生成类配方孤岛生长（文生图/文生视频 zero-asset 节点）= 第二站，不在本批。

## 2. 变更表（蓝图片段 → 实现物）

| 蓝图 | 实现物 | 层 |
|---|---|---|
| 持久图两表 | `models/tables.py: GraphNode / GraphEdge` + Alembic migration。GraphNode：`id / project_id / kind（asset\|document\|generator\|processor\|agent）/ state（draft\|queued\|running\|done\|failed\|skipped\|stale）/ spec JSONB（prompt / params / estimate / 产物引用 output_id / 内部 step 键）/ layout（x, y——画布定居取景，append-only 保序律继承）/ created_at / updated_at`；GraphEdge：`id / project_id / from_node / from_port / to_node / to_port / edge_type（video\|audio\|text\|ctx）` | models + migration |
| graph 服务（wiring 层） | `pipeline/graph_store.py`：`apply_wiring_ops(project_id, ops) -> GraphDelta` 唯一写口（表归属契约不变）——op schema 校验（类型 / 引用存在 / 端口类型相容 / 禁环于 run 子图）+ 单事务落 + 返回受影响节点集 | graph 服务 |
| wiring op 注册表 | op 声明集（add_node{kind, spec, after?} / connect{from, to} / edit_prompt{node, prompt} / delete_node{node} / run{nodes?——缺省 = 受影响子图}）；注册表注入 intent prompt 词表（注册表条目扰动 = prompt 扰动纪律：条目从简 + 门禁枚举） | graph 服务 + chat |
| chat 消费面 | book path：`draft` 的 tasks 载荷**编译为 wiring ops**（add_node + connect 序列——草稿图即「你将得到」，derived preview 干跑投影退役）；`start` = `run(受影响子图)`（出生地仍 = `orchestrator.create_run`）。post-run `chat_intent`：task_list / edit_ops 两型统一为 wiring ops（生成/修订/新建同 op 集）；edit ops（Operation Model clip-spec diff）存活为**节点内部**产物级精修（trim / 字幕样式等参数精确指令） | chat |
| run = 图填充 | `create_run` 扩展入口：从「task list → workflow_steps」扩为「图（子）节点集 → workflow_steps」——每个 generator / processor / agent 节点 = 一个内部 DAG 编译单元（NodeBase 四算子原样消费）；orchestrator 把 step 状态聚合反写节点 state、产物落地反写节点 output_id（**双写方向：steps 是执行账本，图是产品面**） | orchestrator |
| 画布直读 | `GET /projects/{id}/graph`（节点 + 边 + 产物引用一帧）→ FlowView 直渲；`runFlow.ts` 投影适配器**整体删除**（五补丁同亡——grep 零命中是验收条件）；占位物化改为「图本体先存在、产物落地填充节点」（draft state 天然取代 roster 投影） | web |
| 节点卡解剖重构 | FlowNodeCard 按 ADR-057 §4/§5/§6 重构：caption = 类型 icon + 名（**右槽恒空**——状态原地表达，永无角标）；卡体 = draft 虚线空态（「运行后生成 · 约 N 积分」）/ running 擦除（CSS 封顶 96% 律继承）/ done 内容自证 / failed 卡内红；generator 卡面 **prompt 区**（直改）；**factsbar 外置**（卡下 toolbar-row：runtime 事实〔模型 / 参数 / 耗时——OutputInspector 同源〕+ actions）；状态叙事不打勾流第二份 | web |
| 端口法则 | Handle 可见化：**进 = 消费区域最左下角，出 = 生产区域最右上角**；同侧多口从角起堆叠；边按 edge_type 着色（video / audio / text / ctx 虚线）；不可见 Handle（`!h-0 !w-0 !opacity-0`）退役 | web |
| prompt 直改+确认 | 卡面 prompt 编辑 → **定价确认卡**（锚定受影响子图、估价随行——受影响 = 本节点 ∪ 图边下游）→ 发送 = 焦点预钉修订回合骑 `POST /chat` 唯一通道 → `edit_prompt` op + `run(子图)`。永不开新执行通道、永无模型选择器 | web + chat |
| 语义账本塌缩 | `GET /wallet/transactions` 响应加工（服务端投影）：hold / capture / release 折叠为 per-run-event 净额行（「Post 修订 −3」），用户面只显**花费 / 赠送 / 充值**三族；CreditsPill popover 裸 kind 列表删除 | platform + web |
| 任务书 = document 节点 | brief 账本机制零改动（对话引擎状态）；任务书的渲染落点从 dock 卡改挂图（document 节点，FLORA 文本节点形态）；dock 任务书卡保留至图节点接管确认节拍后退役（施工时按 K5 状态裁定） | chat + web |
| i18n + 剧本 | 全部新文案 en.ts 先行 zh.ts 镜像（`Resources` 类型锁）；`scripts/chat_scenarios.py` 横切更新（修订场景走 wiring 断言） | web + scripts |

**不在本批（第二站 / 缓做）**：生成类配方孤岛生长（zero-asset 生成节点）；节点时间线编辑器面（先只给成品感，用户拍板 2026-09-07）；手动布线 UI（永不开放）；血缘板；多 graph per project；节点版本树 UI（versions 状态维度先以变体分页既有形态存活）。

## 3. 拓扑细案（现有管线 → 图的迁移映射）

| 现状（workflow_steps / assets / outputs） | 图节点 | 说明 |
|---|---|---|
| `assets` 行（上传物 / 贴文转写） | **asset** | 上传即落图（asset 节点与 asset 行同生） |
| 任务书（plan 前奏产物）/ `material_understanding` / research brief | **document** | 中间产物升一等公民（FLORA 文本节点形态） |
| `select_clips`（选段编剧 agent） | **generator** | prompt = 选段意图；内部 workflow = 选段 step 族（align_stills / materialize_source 住内部） |
| `dub_clip` / `translate_clip` / `add_music` | **generator** | prompt = 参数化意图（目标语言 / 情绪——卡面可读可改） |
| `write_post` / `write_quotes` / `write_carousel` / `write_article` | **generator** | prompt = 写作指令（brief 账本槽位蒸馏照进 spec，规则不变） |
| `remove_filler` / `render` / 字幕摊铺 | **processor** | 确定性参数化，无 LLM prompt（参数在 factsbar） |
| `research`（BoundedLoopNode） | **agent** | 三护栏原样（max_iterations / 报价 fold / 对外单节点） |
| `outputs` 行 | 节点产物区 | `output_id` 引用反写；node state = 其内部 step 族聚合态（aggregateStatus 逻辑搬进 orchestrator 反写） |

**修订环根治机制**（本批的存在理由）：修订 = `edit_prompt(node)` + `run({node} ∪ downstream)`——下游由**图边遍历**确定（取代 `resolveStepNode` 投影游走）；修订目标 = 图节点 id 确定引用（@ mention / 焦点预钉既有机制原样消费），不再是 run 内 scope 猜测——「Target clip not found」类失败结构性不可能。

**存量数据**：K2 附带一次性回填脚本（从项目最新 run 的 workflow_steps 映射节点 + 边）；dev 阶段允许 `reset_db` 清库重生（回填失败不阻塞批）。pre-run 项目（pending_brief 待确认）= 图空 + dock 待确认原样。

## 4. Commit 切分（每 commit 冷启动自绿：tsc + import + 引导一处真实路径）

- **K1**：两表 + migration + graph 服务 + wiring op 注册表 + MODULE_ARCH §4 登记改写为现状。零行为变化（无消费者）。
- **K2**：`create_run` 图填充路径 + 迁移映射落图 + orchestrator 状态/产物反写 + 回填脚本。**双写期**：workflow_steps 照常（执行账本），图同步落（产品面）；旧前端画布不受扰。
- **K3**：`/graph` 端点 + 画布直读切换 + **runFlow.ts 删除**（五补丁同 commit 火化）+ 节点卡解剖重构 + 端口法则。
- **K4**：prompt 直改 + 定价确认回路 + 修订 = edit_prompt + 子图重跑（修订环根治验收点）+ 语义账本塌缩。
- **K5**：任务书 document 节点化 + 草稿态确认节点锚定 + i18n 全键 + 剧本更新 + 文档现在时改写（CHAT_ARCH §5/§9、DIALOG_WORKFLOW §2.2、MODULE_ARCH §7.1 代码地图、CLAUDE.md 画布段）。

K1→K2→K3 顺序强依赖；K4 依赖 K3（直改落在直读画布上）；K5 依赖 K2。

## 5. 验收

1. **执行内核零改动（硬条）**：`workflow_steps` 粒度 / NodeBase 四算子 / 队列认领 / hold→capture→release 时序——diff 为零或纯加挂（反写钩子）；billing 对账尺（reconcile_credits）复跑四恒等式全绿。
2. **修订环根治（硬条）**：有产物的项目里 chat 说「把 Post 改短一点」→ `edit_prompt` 落图 → 只重跑该节点与图边下游 → 产物原地更新；全程无 Target-not-found 类失败；剧本横切锁定该路径。
3. **草稿态**：新书确认前画布已见全图（节点空态 + 逐节点估价），start 后节点逐填；零消耗直到 run。
4. **零投影（硬条）**：`runFlow.ts` / `canvas_hidden` / `canvas_key` / spine / `resolveAssetFeedTargets` grep 零命中。
5. **直改+确认**：卡面改 prompt → 确认卡估价（锚定子图）→ 发送 → 子图重跑；通道唯一 = POST /chat。
6. **语义账本**：popover 只显三族行，无 hold / capture / release 字样。
7. **agent 言语律**：全部新 agent 文案无内部词汇（wiring / spec / 程序 / 任务书）、无 UI 教学句；动作行一句话原位 morph。
8. S1~S53 无回归（剧本用户自跑）；每 commit tsc / 冷启动绿。

## 6. Prohibited Behaviors

- **禁执行内核改动**：workflow_steps 粒度、NodeBase 四算子、队列认领、hold→capture→release 时序一行不动（本批 = 图的所有权与展示层重建，不是执行层重建）。
- **禁第二执行通道**：wiring ops / 卡面直改全部骑 `POST /chat`；run 出生地唯一 = `orchestrator.create_run`（零旁路原则不变）。
- **禁投影回潮**：不新增任何「领域数据 → 画布」适配层 / 中间视图模型；画布数据源唯一 = graph 直读。
- **禁手动布线 UI**：wiring 能力完备但前端不暴露 connect / delete / drag 手势（拓扑编辑手势物理缺席不变——ADR-035 精神 = 能力完备、手势缺席）。
- **禁内部词汇出 agent 之口**（wiring op / spec / 程序 / 任务书 / 节点 id）；禁 manual-speak UI 教学（「点它卡上的 prompt 直接改」式）；动作行禁叠行。
- **禁模型选择器 / SKU 货架上节点面**（ADR-051 条款 5 不变；runtime 事实住 factsbar，不是控件）。
- **禁时间线编辑器面**：clip 节点只给成品感（用户拍板 2026-09-07；编辑器面后续迭代）。
- **禁账本机器词上 UI**：hold / capture / release / ledger kind 永不直渲。
- **禁 caption 角标**：状态原地表达（draft 虚线 / 擦除 / 内容 / 卡内红），caption 右槽恒空。
- **禁 LLM 簿记上图**：brief 账本五槽永远不住 graph_nodes.spec（两个 brief 同名不同物——账本 = 对话引擎状态，spec = 节点程序）。
