# 画布拓扑时间一致性——剩余验收（ADR-098/113）

> Status: effective rank、settled freeze 与 legacy 混合岛读时归一已有代码层结果；compileall/import、web 类型检查、当前 e2e 与 live 验收仍开放。本文只保留现行拓扑约束和验收，不记录分批施工。

## 1. 当前拓扑契约

- **一个 rank authority**：写时岛/帧分配与读时 `display_ranks` 使用同一 effective 拓扑层；出生帧和后续 `/graph` 不得各吃一张图。服务端 `display_ranks` 与客户端 `projectSettledFrames` 同 fixture 同数。
- **effective 层只读**：纯函数返回投影，不落库、不进入 RunOp 闭包、stale 传播、工作流编译或 worker 认领。执行拓扑仍以 run 内编译事实为准。
- **ADR-113 重基线**：新图没有 transcript 节点，也没有 synthetic transcript→consumer 边；transcript 是资产卡内容。legacy transcript 节点/边只允许在迁移与读兼容层归一，不得再被描述为目标 Effective Product Graph。
- **去重只看 rank 合法边**：lineage/ctx 端口边不占 rank 合成边的去重位置，自环排除；lineage 继续只表达血缘，不产生调度语义。
- **settled rank 冻结**：rank-relevant 的 video/audio/text 边 connect/disconnect 到非 draft 目标必须拒绝；ctx 与 lineage 按既有豁免。`graph_fill` 的对账使用同一谓词，内部操作不获额外豁免。
- **legacy 混合岛读时归一**：跨 effective rank 的旧岛按 rank 拆 cohort，cohort 内序号重定基；单成员 cohort 不生成 corridor、不下发 island/reserved_bottom。存储帧不被裸 SQL 重写。
- 新成员只按 append-only 规则影响自己的座位，既有卡不移动；不为“按实际占据”动态压缩廊道。

## 2. 自动与 live 验收

自动检查：compileall/冷导入、相关 product-graph 与 layout 纯测试、web tsc、当前受影响 e2e。未运行前不得写成通过。

live 至少覆盖：

1. **存量载荷恒等**：同一未迁移项目 `/graph` 的 nodes/edges/rank 与现行读兼容预期一致；若有差异必须能归因到 ADR-113 的明确迁移，而非隐式重排。
2. **legacy 混合岛**：项目 `62594b0b` 或等价夹具显示 rank 0/1/2，无 reserved_bottom 幽灵空列；legacy transcript 仅作读兼容，不被写成新节点。
3. **Start 主链**：lineage/ctx 豁免真实有效，Start 不被 settled-rank 门误杀；执行闭包没有消费 display/effective 边。
4. **素材删除 reflow**：幸存消费者 rank 下降与左移作为具名 lifecycle 后果出现，不被误报为随机布局回归。
5. **多 writer / append-only**：同 rank、同父签名的 writer 归组；新增成员进入下一列时既有卡不动，revealOrder 恒为 from 先于 to。
6. **双端一致与移动端**：服务端和客户端帧数值一致，移动端没有第二 rank 源。

## Prohibited Behaviors

- 禁 effective/display 边落库或进入执行侧；禁恢复 transcript 特判和新 synthetic transcript 拓扑。
- 禁 lineage/ctx 边界暗改，禁给岛内边新增方向豁免。
- 禁拆 topology_rank / layout_rank 双名，禁动态压缩既有廊道。
- 禁裸 SQL 修复存量混合岛，禁改变 worker 认领与 claim-token CAS。
