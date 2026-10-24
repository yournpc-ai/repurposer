# Product Artifact Ontology——剩余合同（ADR-097）

> Status: canonical stamp 与读面投影已有代码层结果；artifact readiness、聚合呈现和真实旅程仍需验收。Phase 2 schema 仅在 Phase 1 验证后另行启动，不是已授权立即实施。

## 1. 当前契约

- 编译期在节点 spec 写 canonical 四字段：`work_key` / `artifact_key` / `artifact_name` / `artifact_role ∈ {deliverable, facet, companion, reference}`。同一交付物的 producer、装配、companion 与隐藏 modifier 显式共享 `artifact_key`。
- `fill_key` 仍是节点幂等复用指纹，和 artifact 身份没有换算关系；`artifact_name` 是展示事实，遵守 ADR-058，手改撤名。
- `is_product_node` 与 `artifact_role` 是两层门：前者决定是不是产品节点，后者决定以何种用户表面出现。无 key 的 legacy 节点为 unknown，永不猜成员。
- `/graph` 可按 artifact_key 聚合交付物卡：current version、facet 摘要与 companion 链接；一个 live output 至多属于一张项目交付物卡，fork 兄弟各自独立，archive 保留历史归属。
- 每个 artifact 至多一个 activity owner；运行与完工是同一图的两个投影，失败时才展开工序定位。
- **ADR-113 后的拓扑边界**：transcript 是资产内容，不再是 artifact、companion 或 graph node。新图不得生成 transcript→consumer 合成边或 transcript artifact；血缘从真实资产/产物关系投影。legacy transcript 行只在迁移/读兼容层处理，不能继续当目标拓扑。
- lineage/display-only 边不参与 stale/invalidation 闭包；调度真值仍是 run 内编译的 step inputs，图边增删不改变编排。

## 2. 当前验收

1. 新跑“上传英文发言视频 → 竖屏金句短片”：素材卡内含 transcript，只有一张目标交付物卡与真实 companion；运行中一个 activity owner，完工由 readiness 驱动。
2. 负向守卫：改变 rank / 边序 / created_at / 共享 output / fill_key 相似度均不改变 artifact 成员；无 key 节点保持 unknown。
3. 一个 live output 至多一张交付物卡；fork 兄弟不互相吞并；archived version 仍可追溯。
4. 修改 transcript overlay 不因 display-only lineage 错误使下游产物失效；新图没有 transcript 节点/合成边。
5. 多次连续请求后，中间站不以独立交付物出现；readiness 词汇在验收中最终定稿，不能把示例文案当成已拍板术语。
6. 当前纯测试、相关矩阵与 live `/graph` 验收按改动面运行；未运行项保持开放。

## 3. Phase 2 门

候选表为 `product_artifact(id, work_id, name, current_version_id)` 与 `artifact_version(id, artifact_id, output_id, version_number, status)`，output 退位为物化结果。只有 Phase 1 的身份、读面和真实旅程验证成立后才细化迁移；只搬 canonical 语义，不重定义，不建第二套 DAG。

## Prohibited Behaviors

- 禁从 rank / 邻接 / step 序 / 深度 / created_at / output 尾位 / 相同 output_ids / fill_key 相似性推断 artifact 成员。
- 禁把 facet 塞进 LEVER_TOOLS、禁 name 当 key、禁 legacy 自动补猜、禁 `cluster_id` 等别名。
- 禁 `output.id == version.id` 偷渡、禁运行/完工双拓扑、禁恢复 transcript artifact 或合成拓扑。
