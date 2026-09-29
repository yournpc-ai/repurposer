# Product Artifact Ontology — 施工简报（ADR-097）

> Status: 拍板待开工（2026-09-30）。Phase 1（canonical JSONB stamp + 读面投影）本简报；Phase 2（schema 身份表）随 Phase 1 验证后另立简报。
> 架构母法 = ADR-097；Product Graph 地基 = ADR-086（零改动）；就绪三合取 = ADR-096 §4。

## Phase 1 施工点

### 1. 编译 stamp（零 schema）

- 编译链在降生节点 spec（JSONB）写入 canonical 四字段：`work_key` / `artifact_key` / `artifact_name` / `artifact_role ∈ {deliverable, facet, companion, reference}`。
- `artifact_key` 由编译器按确认计划项分配，同一交付物的全部相关节点（producer / 装配 / 文档伴侣 / 隐藏 modifier）显式携带同一 key。
- `fill_key` 语义零改动（节点幂等复用指纹），与 `artifact_key` 无任何换算关系。
- `artifact_name` / work 名 = 展示事实，来源守 ADR-058 二源律（LLM 建图命名；手改撤名让座律延伸）。

### 2. 两层门

- 第一层 `is_product_node`（ADR-086）**零改动**——LEVER_TOOLS 保持 modifier 专用。
- 第二层 `artifact_role` 投影（`product_graph.py` 新增独立谓词与投影函数，不改 Product DAG）：决定 product node 以何种用户表面出现。无 key 节点 → `unknown`（legacy 读面，永不猜）。

### 3. 读面投影（/graph）

- 服务端把同 `artifact_key` 的可见节点聚合为交付物卡：当前 version（live output 唯一归属）+ facet 摘要（程序/状态可查）+ companion 链接。
- 一 live output 在项目视图内至多一张交付物卡；fork 兄弟各自独立（per-output 归属，不引入全局 branch 推断）。
- archived version 留历史归属（ADR-091 归档语义不动）。

### 4. Activity Overlay（M3）

- 每 artifact 单一 activity owner：运行时交付物卡携聚合活动态（工序进展），失败才展开工序级定位；与 ADR-087 Activity 合同同座位（read-side，不进 graph write gate）。
- 运行态与完工态 = 同一图的两个投影，禁两套拓扑。

### 5. lineage（F 批收窄并入）

- transcript→artifact 的 lineage 边出生即真实写入；读时合成（A3-lite）退役；legacy 走单一 canonical projection 去重兼容。
- **lineage/display-only 边永不参与 `graph_fill` 的 stale/invalidation 闭包**；调度事实源恒为 run 内编译的 step inputs，新增图边零编排语义。
- 站间实现边退出默认拓扑（不删数据，退出投影）。

## 验收

- 事故同款新跑（上传英文发言视频 → agent 提案「竖屏金句短片」→ 确认）：画布 = 素材 + 转写 + **一张交付物卡** + companion 翻译表；运行中只一个 activity owner；完工 readiness 驱动播报。
- 负向测试全绿（见下）。
- 第 20 次请求走查：画布读作「做过什么工作」，中间站不再以独立交付物出现。

## 负向测试（强制，ADR-097 §10）

- 改 rank / 边序 / created_at / 共享 output / fill_key 相似 → artifact 成员不变；
- 无 key 节点不被猜进任何 artifact（unknown/legacy 直通）；
- 改 transcript `edited_text` → 下游字幕产物不失效；
- 一 live output 至多一张交付物卡；fork 兄弟不互相吞并。

## Prohibited Behaviors

- **读时推断 artifact 成员永禁**——禁从 rank / 邻接 / step 序 / 深度 / created_at / output 归属 / 尾位 / 相同 output_ids / fill_key 相似性推断（ADR-097 §2 第一承重条款）；
- 禁把 facet 塞进 LEVER_TOOLS / `is_product_node`（两层门不得合并）；
- 禁生成第二套 DAG：artifact 分组不产新边、不改 rank、不改依赖；
- 禁 name 当 key 用（展示事实与身份事实永不混用）；
- 禁 legacy 行自动「补猜」key；
- 禁 JSONB 别名垃圾场（`cluster_id` / `deliverable_group` / `work_cluster` 等一切别名永禁——canonical 四字段唯一）；
- 禁 `output.id == version.id` 偷渡（logical version 是用户语义层，output 是物化载体）；
- 禁运行态/完工态双拓扑。

## Phase 2 边界（不在本简报）

`product_artifact(id, work_id, name, current_version_id)` + `artifact_version(id, artifact_id, output_id, version_number, status)`；output 退位纯物化结果；只搬 canonical 字段语义，不重定义。
