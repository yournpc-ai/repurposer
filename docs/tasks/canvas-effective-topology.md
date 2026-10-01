# 画布拓扑时间一致性 — 施工简报（ADR-098）

> Status: 全批待开工。
> 架构母法 = ADR-098；Product Graph 地基 = ADR-086；artifact/lineage 边界 = ADR-097。

## 背景（取证定案）

走查实测：素材 → 转写稿 → 金句卡（write_quotes draft）三节点画布，两列水平净距 124px vs 708px（5.7×，活 payload 证实金句卡 rank=3、x=1572）。根因 = 两张图：岛出生（`_assign_islands`）吃写时拓扑（持久边，两节点同代，cols=2 廊道合法），rank 投影（`display_ranks`）吃读时拓扑（持久边 + A3-lite 读时合成 transcript→consumer，consumer 深度 2）——consumer 被自家廊道挤到 rank 3，廊道第二列结构性永远等不到住户（未来消费者同样被合成边推到深度 2），死列；岛在结果画布零可见 chrome，空隙无解释。另有 latent 交互：lineage 端口标记边（edge_type=text）会占合成去重三元组，artifact 盖章链的 deliverable 将被自己的血缘边顶掉合成边（存量库零行，律法先于首例）。

施工 = 三批：B1 effective 拓扑唯一层 → B2 Z 门守卫 → B3 legacy 读时归一；总验收节后附。

## 批次 B1：Effective Product Graph 唯一层

### 施工点

1. **抽纯函数** `effective_rank_edges(nodes, persisted_edges)` 入 `app/pipeline/product_graph.py`（投影规则 canonical home）：transcript 文档节点 + asset→consumer 物料流边（video/text）⇒ 合成 transcript→consumer text 边。三铁律：① 零图写入（纯数据返回，调用方永不 flush 合成行）；② 三元组去重**只看 rank 合法边**——lineage 端口标记边（`out:lineage`/`in:lineage`）永不占位；③ 自环排除。把 `routes/projects.py` 的内联合成段（A3-lite，~:483-533）整段替换为本函数调用——读面边载荷形状不变（合成行仍以 dict 出生，`from_port="out:text"`）。
2. **写时同吃一层**：`graph_store._assign_layout`/`_assign_islands` 的 `depth_of`/`rank_parents_of` 改吃 `effective_rank_edges([*placed, *newborns], working_edges)` 的结果（~:756-840 与 :562-700，行号以 current HEAD 重核）。出生帧与读时投影同图：consumer 写时即深度 2，岛家庭按（effective 深度，effective 父签名）归组——transcript 与 consumer 天然不同家庭，消费者兄弟组自成岛，单成员家庭不生岛。**禁 transcript 特判**。
3. **`display_ranks` docstring 改写**：构造假设 =「成员共享一个 effective rank 与一个 effective 父签名」。
4. **执行侧零消费探针**：RunOp 闭包 / stale 传播 / 工作流编译不吃 effective 边——纯测试锁（对同一 fixture，执行拓扑输入前后一致）。

### 验收

- canonical fixture（asset + transcript + 1 consumer）：深度 0/1/2、x = 0/524/1048；两节点不同岛、无岛行出生（单成员家庭）。
- transcript + 3 writers：三 writer 同 rank 2、同 x、同岛；transcript 无岛。
- 读面行为恒等：同一存量项目 `/graph` 载荷（nodes/edges/rank）与 B1 前一致（回归即红）。

## 批次 B2：Settled Rank 冻结律门守卫

### 施工点

1. **connect 守卫**（`apply_wiring_ops.add_edge`，~:1012-1051）：rank 三值边（video/audio/text）进 `to_node.state != "draft"` → `WiringRejected`；ctx 边豁免。
2. **disconnect 守卫**（同门 DisconnectOp 落地点，~:1112-1127）：同一谓词。
3. **7b 对账内嵌同谓词**（`graph_fill` ~:1341-1374）：rank 边进非 draft 目标的 disconnect 跳过并具名上报（log/warning 具名，不静默）——「内部」不是豁免理由。
4. Z 两证明的实证查询入测试注释备查（draft→settled rank 边 = 0 的 DB 守卫查询形状）。

### 验收（负向测试四条，纯函数/ stub 套件）

- rank-connect 进 settled → 拒；ctx-connect 进 settled → 放；
- rank-disconnect 进 settled → 拒；rank-connect/disconnect 进 draft → 放（provisional 机器不破）。

## 批次 B3：Legacy mixed island 读时归一

### 施工点

1. `display_ranks`：检测成员跨 effective rank 的岛 → 按 rank 拆 cohort；cohort ≥ 2 享 corridor（slots 记该 cohort 所在带），**cohort 内 seq 重定基**（禁沿用跨 cohort 全局 seq）；单成员 cohort = corridor 全死。
2. corridor 全死 = 三件事一并：`slots` 不记、节点 `spec.island` 不随读面戳出（冻结格 y 与 `reserved_bottom` 不下发，~projects.py:740-749）。存储帧 y 仍是该节点的 server 座位（append-only 不动），客户端对该节点回普通列律。
3. 客户端零改动验证：`layout.ts projectSettledFrames` 机制不动（`x = rank × PITCH` 与 `spec.island` 两入口）；同一 fixture 服务端/客户端双镜像同数（layout.test.ts 加 fixture）。

### 验收

- 事故同构 fixture（asset + transcript + consumer + 混合岛 cols=2）：rank 0/1/2、x = 0/524/1048；`reserved_bottom` 幽灵死（两列无 2200 地板）；合成边 B→C 方向不变量成立。
- legacy 混合岛（transcript + 3 writers）：transcript cohort 死（单成员），writers cohort 保 corridor（同 rank 2 同 x）。
- 第 5 writer 到来：进 writers 岛第二列（rank 3），既有四卡 x 不动（append-only 回归断言）。

## 总验收（几何断言 + 纪律）

- **A**：事故 fixture rank/x 如上；A→B 净 gap 124、B→C 净 gap 184 = 帧宽分档纹理，**非缺陷**（验收不看像素等距，看 rank × PITCH 节奏）。
- **B**：transcript + 3 writers 同列同 x。
- **C**：5 writers 第 5 进下一列，既有不动。
- **D**：货架岛（多素材）加第 5 成员，全部下游 x 不动。
- **E**：方向不变量零违规、零豁免面（ctx/lineage 既有豁免不动）。
- **F**：revealOrder 恒 from 先于 to。
- **G**：服务端 `display_ranks` ≡ 客户端 `projectSettledFrames` 同 fixture 同数；移动端同 payload 无第二 rank 源。
- **素材删除 reflow**：幸存消费者 rank 掉 0 左移 = 显式 lifecycle 后果，**非 regression**（测试只断言行为发生且被命名，不断言不动）。

## Prohibited Behaviors

- 禁 effective 边进执行侧（RunOp 闭包 / stale 传播 / 工作流编译 / worker 认领）；
- 禁 transcript 特判（`role == "transcript"` 类分支永禁——家庭归组只吃 effective rank + effective 父签名）；
- 禁合成边落库（A3 永是读时纯投影，零 GraphEdge 写入；写时消费只在内存）；
- 禁 lineage/ctx 边边界改动（rank 豁免面零 diff；lineage 只占它自己的血缘语义，永不占合成去重）；
- 禁给岛内边开方向不变量豁免（方向律零豁免面新增）；
- 禁拆 rank 双名（topology_rank / layout_rank 二元化永禁——一个 rank authority + 一条 freeze 律）；
- 禁「按实际占据记账」类动态廊道（破 append-only，已否决入 ADR 备查）；
- 禁裸 SQL 修复存量混合岛（读时归一，零迁移）；禁任何 migration 进本批；
- 禁改 worker 认领机制与 claim token CAS（ADR-079 承重面零 diff）；
- 禁动 prompt 面（本批零 prompt 面——prompt_gate 不需要；工作树里既有 prompt 改动属另一批，永不进本批 commit）。
